#!/usr/bin/env python3
"""生成 0001-susfs-hide-modules.patch（内建 hide_modules 补丁）。

锚点已在 Linux v6.12 源码上核对：
  fs/Makefile             —— 追加 obj-$(CONFIG_KSU_SUSFS) += susfs_hide_modules.o
  kernel/module/procfs.c  —— include + m_show() 按 mod->name 跳过整行
  kernel/kallsyms.c       —— include + s_show() 按 iter->module_name 跳过整行
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
T = "\t"


def newfile(rel, gp=None, mode="100644"):
    path = os.path.join(HERE, rel)
    data = open(path, encoding="utf-8").read()
    if not data.endswith("\n"):
        data += "\n"
    lines = data.split("\n")[:-1]
    gp = gp or rel
    out = [
        "diff --git a/%s b/%s" % (gp, gp),
        "new file mode %s" % mode,
        "index 000000000..0000000",
        "--- /dev/null",
        "+++ b/%s" % gp,
        "@@ -0,0 +1,%d @@" % len(lines),
    ]
    out += ["+" + l for l in lines]
    return "\n".join(out) + "\n"


def hunk(old_start, new_start, body, trailing=""):
    """body: 每行自带 ' ' / '+' / '-' 前缀。"""
    lines = body.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    old = sum(1 for l in lines if l[:1] in (" ", "-"))
    new = sum(1 for l in lines if l[:1] in (" ", "+"))
    head = "@@ -%d,%d +%d,%d @@%s" % (old_start, old, new_start, new, trailing)
    return head + "\n" + "\n".join(lines) + "\n"


HEADER = """From: workspace <workspace@localhost>
Subject: [PATCH] susfs: hide selected kernel modules from /proc/modules and /proc/kallsyms

内建版 hide_modules，等价于 susfs4ksu-for-lkm 的可加载模块实现：
  - kernel/module/procfs.c  m_show()  按 module->name 跳过整行（所有读者，含 root）
  - kernel/kallsyms.c       s_show()  按 module_name 跳过整行（模块符号一并消失）
  - /sys/module/<name> 由用户态 ksu_susfs add_sus_path 负责（非 root ENOENT，root 可见）

前置：susfs 主补丁 50_add_susfs_in_gki-*.patch 已应用（本补丁排在其后）。
"""

MAKEFILE = "diff --git a/fs/Makefile b/fs/Makefile\n--- a/fs/Makefile\n+++ b/fs/Makefile\n"
MAKEFILE += hunk(
    24, 24,
    " obj-$(CONFIG_BUFFER_HEAD)\t+= buffer.o mpage.o\n"
    " obj-$(CONFIG_PROC_FS)\t\t+= proc_namespace.o\n"
    "+obj-$(CONFIG_KSU_SUSFS) += susfs_hide_modules.o\n"
    " obj-$(CONFIG_LEGACY_DIRECT_IO)\t+= direct-io.o\n"
    " obj-y\t\t\t\t+= notify/\n",
)

PROCFS = "diff --git a/kernel/module/procfs.c b/kernel/module/procfs.c\n--- a/kernel/module/procfs.c\n+++ b/kernel/module/procfs.c\n"
PROCFS += hunk(
    9, 9,
    " #include <linux/module.h>\n"
    "+#ifdef CONFIG_KSU_SUSFS\n"
    "+#include <linux/susfs_hide_modules.h>\n"
    "+#endif\n"
    " #include <linux/kallsyms.h>\n"
    " #include <linux/mutex.h>\n",
)
PROCFS += hunk(
    74, 77,
    " static int m_show(struct seq_file *m, void *p)\n"
    " {\n"
    " \tstruct module *mod = list_entry(p, struct module, list);\n"
    " \tchar buf[MODULE_FLAGS_BUF_SIZE];\n"
    " \tvoid *value;\n"
    " \tunsigned int size;\n"
    " \n"
    "+#ifdef CONFIG_KSU_SUSFS\n"
    "+\t/* 名单内的模块整行不输出：任何人（含 root）读 /proc/modules 都看不到 */\n"
    "+\tif (susfs_hide_module_name(mod->name))\n"
    "+\t\treturn 0;\n"
    "+#endif\n"
    "+\n"
    " \t/* We always ignore unformed modules. */\n"
    " \tif (mod->state == MODULE_STATE_UNFORMED)\n"
    " \t\treturn 0;\n",
    " static int m_show(struct seq_file *m, void *p)",
)

KALLSYMS = "diff --git a/kernel/kallsyms.c b/kernel/kallsyms.c\n--- a/kernel/kallsyms.c\n+++ b/kernel/kallsyms.c\n"
KALLSYMS += hunk(
    14, 14,
    "  */\n"
    "+#ifdef CONFIG_KSU_SUSFS\n"
    "+#include <linux/susfs_hide_modules.h>\n"
    "+#endif\n"
    " #include <linux/kallsyms.h>\n"
    " #include <linux/init.h>\n",
)
KALLSYMS += hunk(
    728, 731,
    " static int s_show(struct seq_file *m, void *p)\n"
    " {\n"
    " \tvoid *value;\n"
    " \tstruct kallsym_iter *iter = m->private;\n"
    " \n"
    " \t/* Some debugging symbols have no name.  Ignore them. */\n"
    " \tif (!iter->name[0])\n"
    " \t\treturn 0;\n"
    " \n"
    "+#ifdef CONFIG_KSU_SUSFS\n"
    "+\t/*\n"
    "+\t * 模块符号按 module_name 过滤：被藏模块的 __kstrtab_* / *_init / *_exit\n"
    "+\t * 一并消失，避免检测方从 /proc/kallsyms 反推模块存在。\n"
    "+\t */\n"
    "+\tif (iter->module_name[0] &&\n"
    "+\t    susfs_hide_module_symbol(iter->module_name))\n"
    "+\t\treturn 0;\n"
    "+#endif\n"
    "+\n"
    " \tvalue = iter->show_value ? (void *)iter->value : NULL;\n",
    " static int s_show(struct seq_file *m, void *p)",
)

out = (
    HEADER
    + newfile("fs/susfs_hide_modules.c")
    + newfile("include/linux/susfs_hide_modules.h")
    + MAKEFILE
    + PROCFS
    + KALLSYMS
)

dst = os.path.join(HERE, "0001-susfs-hide-modules.patch")
with open(dst, "w", encoding="utf-8") as f:
    f.write(out)
print("written", dst, os.path.getsize(dst), "bytes")
