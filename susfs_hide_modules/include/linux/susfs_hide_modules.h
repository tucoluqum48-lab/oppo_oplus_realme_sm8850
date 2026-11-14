/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_SUSFS_HIDE_MODULES_H
#define _LINUX_SUSFS_HIDE_MODULES_H

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
#endif

#endif /* _LINUX_SUSFS_HIDE_MODULES_H */
