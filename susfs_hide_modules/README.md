# susfs_hide_modules — 内建按名字隐藏内核模块

把指定内核模块从 `/proc/modules` 与 `/proc/kallsyms` 里抹掉，**不引入任何 `.ko`**。
与 `susfs4ksu-for-lkm` 的 `hide_modules` 等价，但走源码补丁。

## 覆盖范围

| 面 | 谁实现 | 效果 |
|---|---|---|
| `/proc/modules` | `kernel/module/procfs.c` 的 `m_show()` 开头 `return 0` | 名单内模块整行不输出（**含 root**） |
| `/proc/kallsyms` | `kernel/kallsyms.c` 的 `s_show()` 按 `module_name` 过滤 | `__kstrtab_*` / `*_init` 等符号一并消失（**含 root**） |
| `/sys/module/<name>` | 用户态 `ksu_susfs add_sus_path`（本补丁不含） | 非 root ENOENT，root 可读 |
| `/proc/crypto`、`comp_algorithm` | 不处理 | 已知短板，与 LKM 版一致 |

## 名单两个来源（取并集）

1. **编译期常量** `susfs_hidden_modules[]`：开机即生效
2. **运行时节点** `/proc/susfs_hide_modules`（0600，仅 root）

```sh
echo "add mymod"   > /proc/susfs_hide_modules
echo "del mymod"   > /proc/susfs_hide_modules
echo "clear"       > /proc/susfs_hide_modules   # 只清运行时表
cat /proc/susfs_hide_modules                    # 看名单 + 命中统计
```

输出示例：

```
compiled: qpace_drv qpace_zram
runtime (2/32): qpace_drv qpace_zram
skipped: modules_lines=2 kallsyms_lines=284
```

## 应用方式

```sh
cd kernel_workspace/common
git apply --whitespace=nowarn ../hide_modules.patch \
  || patch -p1 -F 3 < ../hide_modules.patch
```

补丁改动 5 个文件：

```
新增  fs/susfs_hide_modules.c
新增  include/linux/susfs_hide_modules.h
修改  fs/Makefile             obj-$(CONFIG_KSU_SUSFS) += susfs_hide_modules.o
修改  kernel/module/procfs.c  include + m_show() 跳过
修改  kernel/kallsyms.c       include + s_show() 跳过
```

## 前提

- `CONFIG_KSU_SUSFS=y`
- `CONFIG_KALLSYMS_ALL=y`（否则 `iter->module_name` 为空，kallsyms 过滤空转）

## 重新生成补丁

改动 `fs/`、`include/` 后执行：

```sh
python3 build_patch.py     # 输出 0001-susfs-hide-modules.patch
```
