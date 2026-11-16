/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_OPLUS_MEM_ZONE_H
#define _LINUX_OPLUS_MEM_ZONE_H

#include <linux/types.h>

/*
 * 比 SUSFS 的 AS_FLAGS_SUS_PATH 更狠的一位：sus_path 的原始判定要求
 * "当前进程处于 umounted 状态"，shell/system 这类进程会绕过；
 * hide_modules 给自己标记的路径改用这一位，对所有非 root 生效。
 */
#ifndef AS_FLAGS_SUS_PATH_STRICT
#define AS_FLAGS_SUS_PATH_STRICT 40
#endif

#ifdef CONFIG_KSU_SUSFS
bool susfs_hide_module_name(const char *name);
bool susfs_hide_module_symbol(const char *module_name);
bool susfs_hide_symbol_name(const char *name);

/* priority uid filter：kernel/sys.c 与 block/ioprio.c 会调用 */
bool susfs_prio_uid_filtered(u32 uid);

/* 零宽字符路径拦截：fs/namei.c 的 getname_flags() 调用 */
bool susfs_is_zwc_bypass_path(const char *name, int len);

/* 控制节点对非 root 隐藏：fs/proc/generic.c 的 lookup / readdir 调用 */
bool susfs_proc_name_hidden(const char *name, unsigned int len);

/* sus_path 白名单：名单内 uid 不受 strict 位影响（fs/susfs.c 调用） */
bool susfs_sus_path_uid_allowed(u32 uid);
#else
static inline bool susfs_hide_module_name(const char *name)
{
	return false;
}

static inline bool susfs_hide_module_symbol(const char *module_name)
{
	return false;
}

static inline bool susfs_hide_symbol_name(const char *name)
{
	return false;
}

static inline bool susfs_prio_uid_filtered(u32 uid)
{
	return false;
}

static inline bool susfs_is_zwc_bypass_path(const char *name, int len)
{
	return false;
}

static inline bool susfs_proc_name_hidden(const char *name, unsigned int len)
{
	return false;
}

static inline bool susfs_sus_path_uid_allowed(u32 uid)
{
	return false;
}
#endif

#endif /* _LINUX_OPLUS_MEM_ZONE_H */
