/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_SUSFS_HIDE_MODULES_H
#define _LINUX_SUSFS_HIDE_MODULES_H

#include <linux/types.h>

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
