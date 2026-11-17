#!/usr/bin/env python3
"""生成 0001-susfs-hide-modules.patch（内建 hide_modules 补丁）。

锚点已在 Linux v6.12 源码上核对：
  fs/Makefile             —— 追加 obj-$(CONFIG_KSU_SUSFS) += oplus_mem_zone.o
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
  - /sys/module/<name> 由本模块置 strict 位，对所有非 root 生效（root 仍可见）

前置：susfs 主补丁 50_add_susfs_in_gki-*.patch 已应用（本补丁排在其后）。
"""

MAKEFILE = "diff --git a/fs/Makefile b/fs/Makefile\n--- a/fs/Makefile\n+++ b/fs/Makefile\n"
MAKEFILE += hunk(
    24, 24,
    " obj-$(CONFIG_BUFFER_HEAD)\t+= buffer.o mpage.o\n"
    " obj-$(CONFIG_PROC_FS)\t\t+= proc_namespace.o\n"
    "+obj-$(CONFIG_KSU_SUSFS) += oplus_mem_zone.o\n"
    " obj-$(CONFIG_LEGACY_DIRECT_IO)\t+= direct-io.o\n"
    " obj-y\t\t\t\t+= notify/\n",
)

PROCFS = "diff --git a/kernel/module/procfs.c b/kernel/module/procfs.c\n--- a/kernel/module/procfs.c\n+++ b/kernel/module/procfs.c\n"
PROCFS += hunk(
    9, 9,
    " #include <linux/module.h>\n"
    "+#ifdef CONFIG_KSU_SUSFS\n"
    "+#include <linux/oplus_mem_zone.h>\n"
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
    "+#include <linux/oplus_mem_zone.h>\n"
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
    "+\t/* 符号定义在别的模块里（如厂商 zram 包了 qpace 的压族函数）\n"
    "+\t * 时按模块名抓不到，这里按符号名再抹一次 */\n"
    "+\tif (susfs_hide_symbol_name(iter->name))\n"
    "+\t\treturn 0;\n"
    "+#endif\n"
    "+\n"
    " \tvalue = iter->show_value ? (void *)iter->value : NULL;\n",
    " static int s_show(struct seq_file *m, void *p)",
)


SUSFS_C = "diff --git a/fs/susfs.c b/fs/susfs.c\n--- a/fs/susfs.c\n+++ b/fs/susfs.c\n"
SUSFS_C += hunk(
    1, 1,
    " #include <linux/version.h>\n"
    "+#include <linux/oplus_mem_zone.h>\n"
    " #include <linux/cred.h>\n",
)
# 2.4.0 的 #else 分支只定义了 SUSFS_LOGI/LOGE，漏了 RL 两个宏；
# 未开启 CONFIG_KSU_SUSFS_ENABLE_LOG 时会编译失败，这里补上空定义。
SUSFS_C += hunk(
    46, 46,
    " #else\n"
    " #define SUSFS_LOGI(fmt, ...) \n"
    " #define SUSFS_LOGE(fmt, ...) \n"
    "+#define SUSFS_LOGI_RL(fmt, ...)\n"
    "+#define SUSFS_LOGE_RL(fmt, ...)\n"
    " #endif\n",
)

SUSFS_C += hunk(
    2185, 2185,
    " \t\tSUSFS_LOGE(\"failed to create the thread susfs_priority_app_strings\\n\");\n"
    " \t}\n"
    " }\n"
    " \n"
    "+/* 内核态入口：供 /proc/oplus_mem_zone 下发包名时使用（等价于 supercall 版本的 setter）\n"
    "+ * 只更新包名缓冲并触发重新解析，位图构建与 uid 解析完全复用上游实现。 */\n"
    "+int susfs_kernel_set_priority_apps(const char *apps)\n"
    "+{\n"
    "+\tchar *dup, *old;\n"
    "+\n"
    "+\tif (!apps)\n"
    "+\t\treturn -EINVAL;\n"
    "+\n"
    "+\tdup = kstrdup(apps, GFP_KERNEL);\n"
    "+\tif (!dup)\n"
    "+\t\treturn -ENOMEM;\n"
    "+\n"
    "+\tmutex_lock(&susfs_mutex_lock_priority_uid_filter);\n"
    "+\told = susfs_priority_app_strings;\n"
    "+\tsusfs_priority_app_strings = dup;\n"
    "+\tmutex_unlock(&susfs_mutex_lock_priority_uid_filter);\n"
    "+\tkvfree(old);\n"
    "+\n"
    "+\tsusfs_parse_priority_app_strings();\n"
    "+\treturn 0;\n"
    "+}\n"
    "+\n"
    "+/* 内核态入口：直接按 uid 列表构建位图，不经过包名解析（puid 保底路径） */\n"
    "+int susfs_kernel_set_priority_uids(const char *uids)\n"
    "+{\n"
    "+\tstruct susfs_priority_uid_filter_bitmap *new_bitmap, *old_bitmap = NULL;\n"
    "+\tchar *buf, *token, *saveptr, *end;\n"
    "+\tunsigned int uid;\n"
    "+\n"
    "+\tif (!uids)\n"
    "+\t\treturn -EINVAL;\n"
    "+\n"
    "+\tbuf = kstrdup(uids, GFP_KERNEL);\n"
    "+\tif (!buf)\n"
    "+\t\treturn -ENOMEM;\n"
    "+\n"
    "+\tnew_bitmap = kzalloc(sizeof(*new_bitmap), GFP_KERNEL);\n"
    "+\tif (!new_bitmap) {\n"
    "+\t\tkfree(buf);\n"
    "+\t\treturn -ENOMEM;\n"
    "+\t}\n"
    "+\n"
    "+\tsaveptr = buf;\n"
    "+\twhile ((token = strsep(&saveptr, \", \")) != NULL) {\n"
    "+\t\ttoken = strim(token);\n"
    "+\t\tif (!*token)\n"
    "+\t\t\tcontinue;\n"
    "+\t\tuid = (unsigned int)simple_strtoul(token, &end, 10);\n"
    "+\t\tif (*end)\n"
    "+\t\t\tcontinue;\n"
    "+\t\tif (uid < SUSFS_UID_FILTER_MIN_UID || uid > SUSFS_UID_FILTER_MAX_UID)\n"
    "+\t\t\tcontinue;\n"
    "+\t\tset_bit(uid - SUSFS_UID_FILTER_MIN_UID, new_bitmap->bits);\n"
    "+\t}\n"
    "+\tkfree(buf);\n"
    "+\n"
    "+\tmutex_lock(&susfs_mutex_lock_priority_uid_filter);\n"
    "+\told_bitmap = rcu_dereference_protected(priority_uid_filter_bitmap,\n"
    "+\t\t\tlockdep_is_held(&susfs_mutex_lock_priority_uid_filter));\n"
    "+\trcu_assign_pointer(priority_uid_filter_bitmap, new_bitmap);\n"
    "+\tmutex_unlock(&susfs_mutex_lock_priority_uid_filter);\n"
    "+\tsynchronize_rcu();\n"
    "+\tif (old_bitmap)\n"
    "+\t\tkfree_rcu(old_bitmap, rcu);\n"
    "+\treturn 0;\n"
    "+}\n"
    "+\n"
    " /*\n"
    "  * Lockless lookup for the getpriority/setpriority syscall path.\n",
)

SUSFS_C += hunk(
    803, 803,
    " \t\tSUSFS_LOGE(\"failed to create the thread susfs_sus_path_app_strings\\n\");\n"
    " \t}\n"
    " }\n"
    " \n"
    "+/* 内核态入口：sus_path uid 白名单（按包名，等价于 supercall 版本） */\n"
    "+int susfs_kernel_set_sus_path_apps(const char *apps)\n"
    "+{\n"
    "+\tchar *dup, *old;\n"
    "+\n"
    "+\tif (!apps)\n"
    "+\t\treturn -EINVAL;\n"
    "+\n"
    "+\tdup = kstrdup(apps, GFP_KERNEL);\n"
    "+\tif (!dup)\n"
    "+\t\treturn -ENOMEM;\n"
    "+\n"
    "+\tmutex_lock(&susfs_mutex_lock_sus_path_uid_filter);\n"
    "+\told = susfs_sus_path_app_strings;\n"
    "+\tsusfs_sus_path_app_strings = dup;\n"
    "+\tmutex_unlock(&susfs_mutex_lock_sus_path_uid_filter);\n"
    "+\tkvfree(old);\n"
    "+\n"
    "+\tsusfs_parse_sus_path_app_strings();\n"
    "+\treturn 0;\n"
    "+}\n"
    "+\n"
    " /*\n"
    "  * Lockless lookup for the sus_path hiding path.\n",
)

SUSFS_C += hunk(
    364, 364,
    " __attribute__((hot)) bool susfs_is_inode_sus_path(struct inode *inode)\n"
    " {\n"
    " \tuid_t uid = current_uid().val % 100000;\n"
    " \tstruct fuse_inode *fi = NULL;\n"
    " \n"
    "+\t/* strict 位：hide_modules 给自己标记的路径，对所有非 root 生效\n"
    "+\t * （上游 sus_path 只对当前进程处于 umounted 状态时生效，\n"
    "+\t *   shell / system 这类非 app 进程会绕过，这里补上） */\n"
    "+\tif (inode && inode->i_mapping &&\n"
    "+\t    test_bit(AS_FLAGS_SUS_PATH_STRICT, &inode->i_mapping->flags) &&\n"
    "+\t    current_uid().val != 0 &&\n"
    "+\t    !susfs_is_uid_allowed_for_sus_path(current_uid().val))\n"
    "+\t\treturn true;\n"
    "+\n"
    " \tif (uid < 10000) {\n"
    " \t\treturn false;\n"
    " \t}\n",
)


NAMEI_C = "diff --git a/fs/namei.c b/fs/namei.c\n--- a/fs/namei.c\n+++ b/fs/namei.c\n"
NAMEI_C += hunk(
    21, 21,
    " #include <linux/wordpart.h>\n"
    " #include <linux/fs.h>\n"
    "+#ifdef CONFIG_KSU_SUSFS\n"
    "+#include <linux/oplus_mem_zone.h>\n"
    "+#endif\n"
    " #include <linux/filelock.h>\n",
)
NAMEI_C += hunk(
    160, 160,
    " \t\t/* The empty path is special. */\n"
    " \t\tif (!(flags & LOOKUP_EMPTY)) {\n"
    " \t\t\t__putname(result);\n"
    " \t\t\treturn ERR_PTR(-ENOENT);\n"
    " \t\t}\n"
    " \t}\n"
    "+\n"
    "+#ifdef CONFIG_KSU_SUSFS\n"
    "+\t/*\n"
    "+\t * 零宽字符 / 可忽略码点绕过 Android/data 隔离：\n"
    "+\t * 返回 -ENOENT 而不是 -EINVAL —— 前者与\"路径不存在\"无法区分，\n"
    "+\t * 后者会让检测方看出\"内核主动拒绝了这条路径\"。\n"
    "+\t */\n"
    "+\tif (unlikely(susfs_is_zwc_bypass_path(kname, len))) {\n"
    "+\t\t__putname(result);\n"
    "+\t\treturn ERR_PTR(-ENOENT);\n"
    "+\t}\n"
    "+#endif\n"
    " \n"
    " \t/*\n"
    " \t * Uh-oh. We have a name that's approaching PATH_MAX. Allocate a\n",
)

GENERIC_C = "diff --git a/fs/proc/generic.c b/fs/proc/generic.c\n--- a/fs/proc/generic.c\n+++ b/fs/proc/generic.c\n"
GENERIC_C += (
    "@@ -12,4 +12,8 @@\n"
    " #include <linux/cache.h>\n"
    "+#ifdef CONFIG_KSU_SUSFS\n"
    "+#include <linux/oplus_mem_zone.h>\n"
    "+#endif\n"
    "+\n"
    " #include <linux/errno.h>\n"
    " #include <linux/time.h>\n"
    " #include <linux/proc_fs.h>\n"
)
GENERIC_C += hunk(
    243, 250,
    " struct dentry *proc_lookup_de(struct inode *dir, struct dentry *dentry,\n"
    " \t\t\t      struct proc_dir_entry *de)\n"
    " {\n"
    " \tstruct inode *inode;\n"
    " \n"
    "+#ifdef CONFIG_KSU_SUSFS\n"
    "+\t/* 控制节点对非 root 完全不可见（lookup 层） */\n"
    "+\tif (susfs_proc_name_hidden(dentry->d_name.name, dentry->d_name.len))\n"
    "+\t\treturn ERR_PTR(-ENOENT);\n"
    "+#endif\n"
    " \tread_lock(&proc_subdir_lock);\n",
)
GENERIC_C += hunk(
    300, 316,
    " \tdo {\n"
    " \t\tstruct proc_dir_entry *next;\n"
    "+#ifdef CONFIG_KSU_SUSFS\n"
    "+\t\t/* 控制节点对非 root 从目录列举里消失（readdir 层） */\n"
    "+\t\tif (susfs_proc_name_hidden(de->name, de->namelen)) {\n"
    "+\t\t\tnext = pde_subdir_next(de);\n"
    "+\t\t\tde = next;\n"
    "+\t\t\tif (!de) {\n"
    "+\t\t\t\tread_unlock(&proc_subdir_lock);\n"
    "+\t\t\t\treturn 1;\n"
    "+\t\t\t}\n"
    "+\t\t\tcontinue;\n"
    "+\t\t}\n"
    "+#endif\n"
    " \t\tpde_get(de);\n",
)


out = (
    HEADER
    + newfile("fs/oplus_mem_zone.c")
    + newfile("include/linux/oplus_mem_zone.h")
    + MAKEFILE
    + PROCFS
    + KALLSYMS
    + SUSFS_C
    + NAMEI_C
    + GENERIC_C
)

dst = os.path.join(HERE, "0001-susfs-hide-modules.patch")
with open(dst, "w", encoding="utf-8") as f:
    f.write(out)
print("written", dst, os.path.getsize(dst), "bytes")
