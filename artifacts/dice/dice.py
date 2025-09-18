#!/usr/bin/env python3
"""
DICE: Dependency-Aware Configuration Debloating
"""

import json
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import kconfiglib
import networkx as nx


class ValidationResult(Enum):
    SUCCESS = "success"
    INVALID_CONFIG = "invalid_config"
    BUILD_FAIL = "build_fail"
    BOOT_FAIL = "boot_fail"
    RUNTIME_FAIL = "runtime_fail"

@dataclass
class ConfigCandidate:
    """Represents a configuration candidate for testing"""
    config: Dict[str, str]  # symbol -> value mapping
    disabled_symbols: Set[str] = field(default_factory=set)
    validation_result: Optional[ValidationResult] = None
    build_time: Optional[float] = None
    size_reduction: Optional[float] = None

class DependencyAnalyzer:
    """Analyzes Kconfig dependency relationships using kconfiglib"""

    def __init__(self, kconfig: kconfiglib.Kconfig):
        self.kconfig = kconfig
        self.dep_graph = self._build_dependency_graph()
        self.reverse_deps = self._build_reverse_dependencies()
        self.choice_groups = self._extract_choice_groups()

    def _build_dependency_graph(self) -> nx.DiGraph:
        """Build directed graph of symbol dependencies"""
        G = nx.DiGraph()

        # Add all symbols as nodes
        for sym in self.kconfig.unique_defined_syms:
            G.add_node(sym.name, symbol=sym, type="symbol")

        # Add choices as nodes
        for choice in self.kconfig.unique_choices:
            choice_id = f"choice_{id(choice)}"
            G.add_node(choice_id, choice=choice, type="choice")

        # Add dependency edges
        for sym in self.kconfig.unique_defined_syms:
            self._add_symbol_dependencies(G, sym)

        return G

    def _add_symbol_dependencies(self, G: nx.DiGraph, sym: kconfiglib.Symbol):
        """Add all dependency relationships for a symbol"""

        # Direct dependencies (depends on)
        for dep_sym in kconfiglib.expr_items(sym.direct_dep):
            if isinstance(dep_sym, kconfiglib.Symbol) and not dep_sym.is_constant:
                G.add_edge(dep_sym.name, sym.name, type="depends_on")

        # Select relationships
        for select_sym, cond in sym.selects:
            G.add_edge(sym.name, select_sym.name, type="select")
            # Add condition dependencies
            for cond_sym in kconfiglib.expr_items(cond):
                if isinstance(cond_sym, kconfiglib.Symbol) and not cond_sym.is_constant:
                    G.add_edge(cond_sym.name, sym.name, type="select_condition")

        # Imply relationships
        for imply_sym, cond in sym.implies:
            G.add_edge(sym.name, imply_sym.name, type="imply")

        # Choice relationships
        if sym.choice:
            choice_id = f"choice_{id(sym.choice)}"
            G.add_edge(choice_id, sym.name, type="choice_member")

    def _build_reverse_dependencies(self) -> Dict[str, Set[str]]:
        """Build reverse dependency mapping for fast lookups"""
        reverse_deps = {}
        for node in self.dep_graph.nodes():
            reverse_deps[node] = set()

        for source, target, data in self.dep_graph.edges(data=True):
            reverse_deps[target].add(source)

        return reverse_deps

    def _extract_choice_groups(self) -> Dict[str, List[str]]:
        """Extract choice groups and their members"""
        choice_groups = {}
        for choice in self.kconfig.unique_choices:
            choice_id = f"choice_{id(choice)}"
            members = [sym.name for sym in choice.syms]
            choice_groups[choice_id] = members
        return choice_groups

    def _build_selected_by_map(self) -> Dict[str, Set[str]]:
        """Return a map: target symbol -> set of symbols that select it"""
        selected_by = {}
        for sym in self.kconfig.unique_defined_syms:
            for target_sym, cond in sym.selects:
                if target_sym.name not in selected_by:
                    selected_by[target_sym.name] = set()
                selected_by[target_sym.name].add(sym.name)
        return selected_by

    def get_dependents(self, symbol: str) -> Set[str]:
        """Get all symbols that depend on the given symbol"""
        if symbol not in self.dep_graph:
            return set()
        return set(self.dep_graph.successors(symbol))

    def get_dependencies(self, symbol: str) -> Set[str]:
        """Get all symbols that the given symbol depends on"""
        if symbol not in self.dep_graph:
            return set()
        return set(self.dep_graph.predecessors(symbol))

    def find_strongly_connected_components(self) -> List[Set[str]]:
        """Find dependency cycles (SCCs) in the configuration"""
        return [set(scc) for scc in nx.strongly_connected_components(self.dep_graph)]

    def compute_removal_impact(self, symbols: Set[str]) -> Dict[str, Set[str]]:
        """Compute what would be affected by removing given symbols"""
        impact = {
            "directly_affected": set(),
            "transitively_affected": set(),
            "choice_conflicts": set()
        }

        for symbol in symbols:
            # Direct dependents
            direct_deps = self.get_dependents(symbol)
            impact["directly_affected"].update(direct_deps)

            # Check choice conflicts
            for choice_id, members in self.choice_groups.items():
                if symbol in members and len([m for m in members if m not in symbols]) == 0:
                    impact["choice_conflicts"].add(choice_id)

        # Compute transitive closure
        all_affected = impact["directly_affected"].copy()
        worklist = list(impact["directly_affected"])

        while worklist:
            current = worklist.pop()
            deps = self.get_dependents(current)
            new_deps = deps - all_affected
            all_affected.update(new_deps)
            worklist.extend(new_deps)

        impact["transitively_affected"] = all_affected
        return impact

class ConfigValidator:
    """Validates configuration candidates through build/boot/runtime testing"""

    def __init__(self, kernel_path: str, build_dir: str = None,
                 boot_test_cmd: str = None, runtime_test_cmd: str = None):
        self.kernel_path = Path(kernel_path)
        self.build_dir = Path(build_dir) if build_dir else self.kernel_path / "build"
        self.boot_test_cmd = boot_test_cmd
        self.runtime_test_cmd = runtime_test_cmd

    def validate_config(self, candidate: ConfigCandidate) -> ValidationResult:
        """Full validation pipeline: config -> build -> boot -> runtime"""

        # Stage 1: Validate Kconfig constraints
        if not self._validate_kconfig_constraints(candidate):
            candidate.validation_result = ValidationResult.INVALID_CONFIG
            return ValidationResult.INVALID_CONFIG

        # Stage 2: Test build
        if not self._test_build(candidate):
            candidate.validation_result = ValidationResult.BUILD_FAIL
            return ValidationResult.BUILD_FAIL

        # Stage 3: Test boot (if configured)
        if self.boot_test_cmd and not self._test_boot(candidate):
            candidate.validation_result = ValidationResult.BOOT_FAIL
            return ValidationResult.BOOT_FAIL

        # Stage 4: Test runtime (if configured)
        if self.runtime_test_cmd and not self._test_runtime(candidate):
            candidate.validation_result = ValidationResult.RUNTIME_FAIL
            return ValidationResult.RUNTIME_FAIL

        candidate.validation_result = ValidationResult.SUCCESS
        return ValidationResult.SUCCESS

    def _validate_kconfig_constraints(self, candidate: ConfigCandidate) -> bool:
        """Validate that configuration satisfies Kconfig constraints"""
        try:
            # Parse Kconfig for the target kernel tree
            os.environ.setdefault("srctree", str(self.kernel_path))
            kconf = kconfiglib.Kconfig(filename=str(self.kernel_path / "Kconfig"),
                                    suppress_traceback=True)

            # Apply candidate values directly via kconfiglib
            attempted = []
            for full, val in candidate.config.items():
                # full is like "CONFIG_FOO"
                name = full[7:] if full.startswith("CONFIG_") else full
                sym = kconf.syms.get(name)
                if not sym:
                    continue
                sym.set_value(val)
                attempted.append(sym)

            # Let kconfig compute final values, then ensure our forced settings stuck
            for sym in attempted:
                if sym.user_value is not None and sym.str_value != sym.user_value:
                    return False
            return True

        except Exception as e:
            print(f"Kconfig validation error: {e}")
            return False

    def _test_build(self, candidate: ConfigCandidate) -> bool:
        """Test if configuration builds successfully"""
        try:
            # Create build directory
            self.build_dir.mkdir(parents=True, exist_ok=True)

            # Produce a correct .config using kconfiglib
            os.environ.setdefault("srctree", str(self.kernel_path))
            kconf = kconfiglib.Kconfig(filename=str(self.kernel_path / "Kconfig"),
                                    suppress_traceback=True)

            # Start from empty; apply only our intended overrides
            for full, val in candidate.config.items():
                name = full[7:] if full.startswith("CONFIG_") else full
                sym = kconf.syms.get(name)
                if sym:
                    sym.set_value(val)

            config_path = self.build_dir / ".config"
            kconf.write_config(str(config_path))

            # Normalize with olddefconfig
            cmd = ["make", f"O={self.build_dir}", "-C", str(self.kernel_path), "olddefconfig"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                return False

            # Build kernel
            import time
            start_time = time.time()
            cmd = ["make", f"O={self.build_dir}", "-C", str(self.kernel_path), "-j", str(os.cpu_count())]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            candidate.build_time = time.time() - start_time

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            print(f"Build test error: {e}")
            return False

    def _test_boot(self, candidate: ConfigCandidate) -> bool:
        """Test if kernel boots successfully"""
        if not self.boot_test_cmd:
            return True

        try:
            result = subprocess.run(self.boot_test_cmd, shell=True,
                                  capture_output=True, text=True, timeout=600)
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            print(f"Boot test error: {e}")
            return False

    def _test_runtime(self, candidate: ConfigCandidate) -> bool:
        """Test runtime functionality"""
        if not self.runtime_test_cmd:
            return True

        try:
            result = subprocess.run(self.runtime_test_cmd, shell=True,
                                  capture_output=True, text=True, timeout=1800)
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            print(f"Runtime test error: {e}")
            return False

class DICEDebloater:
    """Main DICE implementation for kernel configuration debloating"""

    def __init__(self, kernel_path: str, base_config: str = None):
        self.kernel_path = Path(kernel_path)

        # # Initialize kconfiglib
        # os.chdir(kernel_path)
        # self.kconfig = kconfiglib.Kconfig(suppress_traceback=True)
        # Initialize kconfiglib without changing global CWD
        os.environ.setdefault("srctree", str(self.kernel_path))
        self.kconfig = kconfiglib.Kconfig(filename=str(self.kernel_path / "Kconfig"),
                                  suppress_traceback=True)

        # Load base configuration
        if base_config:
            self.kconfig.load_config(base_config)
        else:
            # Use current .config or defconfig
            if (self.kernel_path / ".config").exists():
                self.kconfig.load_config(".config")
            else:
                print("No base config specified and no .config found")

        self.analyzer = DependencyAnalyzer(self.kconfig)
        self.validator = ConfigValidator(kernel_path)

        # Track results
        self.tested_configs = []
        self.best_config = None

    def get_current_config(self) -> Dict[str, str]:
        """Get current configuration as symbol->value mapping"""
        config = {}
        for sym in self.kconfig.unique_defined_syms:
            if sym.str_value != "n":
                config[f"CONFIG_{sym.name}"] = sym.str_value
        return config

    def identify_removal_candidates(self) -> List[Tuple[str, Set[str]]]:
        """Identify good candidates for removal using dependency analysis"""
        candidates = []

        # Find leaf nodes (no dependents) - safest to remove
        for sym in self.kconfig.unique_defined_syms:
            if sym.str_value != "n":
                dependents = self.analyzer.get_dependents(sym.name)
                if not dependents:
                    candidates.append((f"leaf_{sym.name}", {sym.name}))

        # Find weakly connected components
        sccs = self.analyzer.find_strongly_connected_components()
        for i, scc in enumerate(sccs):
            if len(scc) > 1:  # Actual cycle
                candidates.append((f"scc_{i}", scc))

        # Find subsystem clusters based on menu hierarchy
        node = self.kconfig.top_node.list
        while node:
            if node.item == kconfiglib.MENU:
                subsystem_syms = self._get_menu_symbols(node)
                if len(subsystem_syms) > 1:
                    candidates.append((f"menu_{node.prompt[0]}", subsystem_syms))
            node = node.next

        return candidates

    def _get_menu_symbols(self, menu_node) -> Set[str]:
        """Recursively get all symbols under a menu"""
        symbols = set()

        current = menu_node.list
        while current:
            if isinstance(current.item, kconfiglib.Symbol):
                symbols.add(current.item.name)
            elif current.item == kconfiglib.MENU:
                symbols.update(self._get_menu_symbols(current))
            current = current.next

        return symbols

    def guided_search(self, max_iterations: int = 100) -> ConfigCandidate:
        """Main guided search algorithm"""
        print("Starting DICE guided search...")

        # Start with current configuration
        base_config = self.get_current_config()
        best_candidate = ConfigCandidate(config=base_config.copy())

        # Validate base configuration
        print("Validating base configuration...")
        if self.validator.validate_config(best_candidate) != ValidationResult.SUCCESS:
            print("ERROR: Base configuration does not validate!")
            return best_candidate

        print(f"Base configuration valid. Size: {len(base_config)} symbols")
        self.best_config = best_candidate

        # Get removal candidates
        candidates = self.identify_removal_candidates()
        print(f"Found {len(candidates)} removal candidate groups")

        # Iterative removal with backtracking
        for iteration in range(max_iterations):
            print(f"\nIteration {iteration + 1}/{max_iterations}")

            # Try each candidate group
            improved = False
            for candidate_name, symbols_to_remove in candidates:

                # Skip if symbols already removed
                if all(sym not in self.best_config.config for sym in symbols_to_remove):
                    continue

                print(f"  Testing removal of {candidate_name}: {len(symbols_to_remove)} symbols")

                # Skip removal if any symbol is selected by an enabled selector
                skip = False
                for sym in symbols_to_remove:
                    if sym in self.analyzer.selected_by:
                        for selector in self.analyzer.selected_by[sym]:
                            selector_key = f"CONFIG_{selector}"
                            if selector_key in self.best_config.config and self.best_config.config[selector_key] == "y":
                                print(f"    SKIP: {sym} is selected by enabled symbol {selector}")
                                skip = True
                                break
                    if skip:
                        break
                if skip:
                    continue

                # Create new candidate
                new_config = self.best_config.config.copy()
                removed_symbols = set()

                for sym in symbols_to_remove:
                    config_sym = f"CONFIG_{sym}" if not sym.startswith("CONFIG_") else sym
                    # Force-disable explicitly so Kconfig can't re-enable via defaults/selects
                    new_config[config_sym] = "n"
                    removed_symbols.add(config_sym)

                if not removed_symbols:
                    continue

                candidate = ConfigCandidate(
                    config=new_config,
                    disabled_symbols=self.best_config.disabled_symbols | removed_symbols
                )

                # Validate candidate
                result = self.validator.validate_config(candidate)
                self.tested_configs.append(candidate)

                print(f"    Result: {result.value}")

                if result == ValidationResult.SUCCESS:
                    # Found improvement
                    reduction = len(removed_symbols)
                    candidate.size_reduction = reduction
                    print(f"    SUCCESS: Removed {reduction} symbols")
                    self.best_config = candidate
                    improved = True
                    break
                else:
                    # Try removing smaller subsets if this was a large group
                    if len(symbols_to_remove) > 5:
                        print("    Large group failed, trying bisection...")
                        self._try_bisection_removal(symbols_to_remove, self.best_config)

            if not improved:
                print("No improvements found, search complete.")
                break

        return self.best_config

    def _try_bisection_removal(self, symbols: Set[str], base_candidate: ConfigCandidate):
        """Try removing smaller subsets using bisection"""
        symbols_list = list(symbols)

        # Try first half
        first_half = set(symbols_list[:len(symbols_list)//2])
        if first_half:
            new_config = base_candidate.config.copy()
            removed_symbols = set()

            for sym in first_half:
                config_sym = f"CONFIG_{sym}" if not sym.startswith("CONFIG_") else sym
                new_config[config_sym] = "n"
                removed_symbols.add(config_sym)

            if removed_symbols:
                candidate = ConfigCandidate(
                    config=new_config,
                    disabled_symbols=base_candidate.disabled_symbols | removed_symbols
                )

                result = self.validator.validate_config(candidate)
                print(f"      Bisection first half: {result.value}")

                if result == ValidationResult.SUCCESS:
                    candidate.size_reduction = len(removed_symbols)
                    self.best_config = candidate

    def save_results(self, output_path: str):
        """Save debloating results"""
        results = {
            "base_config_size": len(self.get_current_config()),
            "final_config_size": len(self.best_config.config),
            "symbols_removed": len(self.best_config.disabled_symbols),
            "reduction_percentage": (len(self.best_config.disabled_symbols) /
                                   len(self.get_current_config())) * 100,
            "total_tests": len(self.tested_configs),
            "final_config": dict(self.best_config.config),
            "removed_symbols": list(self.best_config.disabled_symbols)
        }

        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        # Also save the final .config
        config_path = Path(output_path).with_suffix('.config')
        with open(config_path, 'w') as f:
            for symbol, value in self.best_config.config.items():
                if value == 'n':
                    f.write(f"# {symbol} is not set\n")
                else:
                    f.write(f"{symbol}={value}\n")

        print(f"Results saved to {output_path}")
        print(f"Final config saved to {config_path}")

def main():
    """Example usage"""
    import argparse

    parser = argparse.ArgumentParser(description="DICE: Dependency-Aware Configuration Debloating")
    parser.add_argument("kernel_path", help="Path to kernel source tree")
    parser.add_argument("--base-config", help="Base configuration file")
    parser.add_argument("--output", default="dice_results.json", help="Output file for results")
    parser.add_argument("--max-iterations", type=int, default=50, help="Maximum search iterations")
    parser.add_argument("--boot-test", help="Command to test kernel boot")
    parser.add_argument("--runtime-test", help="Command to test runtime functionality")

    args = parser.parse_args()

    # Initialize DICE
    debloater = DICEDebloater(args.kernel_path, args.base_config)

    # Configure validation
    if args.boot_test:
        debloater.validator.boot_test_cmd = args.boot_test
    if args.runtime_test:
        debloater.validator.runtime_test_cmd = args.runtime_test

    # Run guided search
    try:
        final_config = debloater.guided_search(args.max_iterations)
        debloater.save_results(args.output)

        print("\nDICE completed successfully!")
        print(f"Original config: {len(debloater.get_current_config())} symbols")
        print(f"Final config: {len(final_config.config)} symbols")
        print(f"Reduction: {len(final_config.disabled_symbols)} symbols")

    except KeyboardInterrupt:
        print("\nSearch interrupted by user")
        if debloater.best_config:
            debloater.save_results(args.output)
    except Exception as e:
        print(f"Error during search: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
