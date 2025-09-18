#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/sched/signal.h>  // for_each_process
#include <linux/mm.h>
#include <linux/highmem.h>
#include <linux/slab.h>
#include <asm/pgtable.h>
#include <asm/uaccess.h>
#include <asm/io.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Gee");
MODULE_DESCRIPTION("Dump process info with CR3 register (PGD phys addr)");

static int __init cr3_dump_init(void)
{
    struct task_struct *task;

    printk(KERN_INFO "=== [CR3 Dump Module Loaded] ===\n");

    for_each_process(task) {
        struct mm_struct *mm = task->mm;
        if (!mm)
            mm = task->active_mm;
        if (!mm)
            continue;

        // Get CR3 equivalent (physical address of PGD)
        unsigned long cr3 = virt_to_phys(mm->pgd);

        printk(KERN_INFO "PID: %d | Comm: %s | CR3 (PGD phys): 0x%lx\n",
               task->pid, task->comm, cr3);
    }

    return 0;
}

static void __exit cr3_dump_exit(void)
{
    printk(KERN_INFO "=== [CR3 Dump Module Unloaded] ===\n");
}

module_init(cr3_dump_init);
module_exit(cr3_dump_exit);
