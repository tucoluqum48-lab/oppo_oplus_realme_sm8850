# susfs 内建 hide_modules（路线一）

把指定内核模块从 `/proc/modules` 与 `/proc/kallsyms` 里抹掉，等价于
`susfs4ksu-for-lkm` 的 `hide_modules`，但不引入任何 `.ko`。

| 层 | 谁实现 | 效果 |
|---|---|---|
| `/proc/modules` | `kernel/module/procfs.c` 的 `m_show()` 开头 `return 0` | 名单内模块整行不输出，**所有读者（含 root）都看不到** |
| `/proc/kallsyms` | `kernel/kallsyms.c` 的 `s_show()` 开头按 `module_name` 过滤 | 该模块的 `__kstrtab_*` / `*_init` / `*_exit` 等符号一并消失 |
| `/sys/module/<name>` | 用户态 `ksu_susfs add_sus_path /sys/module/<name>` | 非 root 得到 `ENOENT`，root 仍可读（与 LKM 版同一个不对称） |

**不需要新增 Kconfig 项、不需要改 defconfig**：全部复用已有的 `CONFIG_KSU_SUSFS`。

## 文件清单

```
0001-susfs-hide-modules.patch   内核补丁（在 GKI android16-6.12 真实源码上 git apply 校验通过）
fs/susfs_hide_modules.c         名单 + 判定函数（补丁会新建）
include/linux/susfs_hide_modules.h  声明（补丁会新建）
build_patch.py                  重新生成补丁用（改了名单文件后可重跑）
```

## 一、填名单

编辑 `fs/susfs_hide_modules.c` 的数组，名字必须是 `struct module->name`，
也就是设备上 `lsmod` 第一列 / `cat /proc/modules` 第一列，**不带 `.ko`，下划线原样**：

```sh
adb shell 'lsmod'          # 或 su -c lsmod
# 输出示例：
# Module                  Size  Used by
# zygisk_loader         123456  0
# susfs_guard_lkm        98765  0
```

```c
static const char *const susfs_hidden_modules[] = {
	"zygisk_loader",
};
```

填完跑一次 `python3 build_patch.py` 重新生成补丁（否则补丁里的文件内容还是旧的占位符）。

> 名字拿不准就先在设备上 `cat /proc/modules | cut -d' ' -f1`。
> 藏错名字不会崩，只是没效果。

## 二、集成到构建（三种方式，任选）

### 方式 A：直接改源码（最省事）

把两个新文件放到内核树对应位置，然后手改三处：

1. `fs/Makefile`，在 `obj-$(CONFIG_KSU_SUSFS) += susfs.o` 下一行加
   ```make
   obj-$(CONFIG_KSU_SUSFS) += susfs_hide_modules.o
   ```
2. `kernel/module/procfs.c`
   - `#include <linux/module.h>` 后面加
     ```c
     #ifdef CONFIG_KSU_SUSFS
     #include <linux/susfs_hide_modules.h>
     #endif
     ```
   - `m_show()` 里，`unsigned int size;` 之后加
     ```c
     #ifdef CONFIG_KSU_SUSFS
     	/* 名单内的模块整行不输出 */
     	if (susfs_hide_module_name(mod->name))
     		return 0;
     #endif
     ```
3. `kernel/kallsyms.c`
   - 顶部 `#include <linux/kallsyms.h>` 之前加同样的 `#ifdef` 包含块
   - `s_show()` 里，`if (!iter->name[0]) return 0;` 之后加
     ```c
     #ifdef CONFIG_KSU_SUSFS
     	if (iter->module_name[0] &&
     	    susfs_hide_module_name(iter->module_name))
     		return 0;
     #endif
     ```

### 方式 B：打补丁

补丁排在 susfs 主补丁**之后**：

```sh
cd ./common
patch -p1 -F 3 < 50_add_susfs_in_gki-$ANDROID_VERSION-$KERNEL_VERSION.patch
patch -p1 -F 3 < 0001-susfs-hide-modules.patch
```

⚠️ 不要给这行加 `|| true`。上面的 `grep` 校验能挡住"静默跳过"：

```sh
grep -q susfs_hide_module_name kernel/module/procfs.c || { echo "hide_modules 补丁没打上"; exit 1; }
grep -q susfs_hide_module_name kernel/kallsyms.c     || { echo "hide_modules 补丁没打上"; exit 1; }
```

### 方式 C：接进 fastbuild workflow

`fastbuild_6.12.23-susfs-hidden.yml` 里，第 295 行那个
`- name: 应用 KernelSU & SUSFS 补丁` 步骤之后，插一个新步骤：

```yaml
      - name: 应用 hide_modules 补丁
        if: inputs.susfs_enable
        run: |
          cd ${{ github.workspace }}/kernel_manifest   # 换成你 clone 出来的内核目录
          cp ${{ github.workspace }}/susfs-hide-modules/fs/susfs_hide_modules.c ./common/fs/
          cp ${{ github.workspace }}/susfs-hide-modules/include/linux/susfs_hide_modules.h ./common/include/linux/
          cd ./common
          patch -p1 -F 3 < ${{ github.workspace }}/susfs-hide-modules/0001-susfs-hide-modules.patch
          grep -q susfs_hide_module_name kernel/module/procfs.c || exit 1
          grep -q susfs_hide_module_name kernel/kallsyms.c     || exit 1
```

（把 `kernel_manifest` 换成你 workdir 里实际的内核源码目录；两个新文件也可以直接提交进仓库，
用 `wget raw.githubusercontent.com/.../susfs_hide_modules.c` 拉。）

## 三、开机后补 `/sys/module`

内核侧只能改 `/proc` 输出，`/sys/module/<name>/` 目录得用现成的 sus_path：

```sh
# /data/adb/service.d/99-hide-modules.sh，等模块都加载完再跑
sleep 60
for m in zygisk_loader; do
    [ -d "/sys/module/$m" ] && ksu_susfs add_sus_path "/sys/module/$m"
done
```

## 四、验证

编译后、刷机前先确认代码真的进了 `Image`：

```sh
# vmlinux 里应该有这个字符串数组内容与函数符号
strings vmlinux | grep -x "zygisk_loader"
```

刷机后（**注意：`m_show` 是无条件的，root 也看不到**）：

```sh
# 1) /proc/modules —— 谁都看不到
adb shell 'cat /proc/modules' | grep -c zygisk_loader     # → 0
adb shell 'su -c cat /proc/modules' 2>/dev/null | grep -c zygisk_loader   # → 0

# 2) /proc/kallsyms —— 模块符号也没了
adb shell 'grep -c zygisk_loader /proc/kallsyms'          # → 0

# 3) /sys/module —— 只有非 root 看不到
adb shell 'ls /sys/module' | grep -c zygisk_loader        # → 0（Permission denied 也算）
adb shell 'su -c ls /sys/module' | grep -c zygisk_loader  # → 1，root 仍可见，预期如此
```

第三条的反差是设计上的，和 LKM 版一致：模块参数在 `/sys/module/<name>/parameters` 里，
把 root 也挡掉会连带影响正常工具。

## 五、回滚

```sh
git checkout -- fs/Makefile kernel/module/procfs.c kernel/kallsyms.c
rm -f fs/susfs_hide_modules.c include/linux/susfs_hide_modules.h
```

或者把 `fs/susfs_hide_modules.c` 的数组清空（留一个不存在的名字），重编即可：
过滤代码还在，但没有命中项，行为等于关闭。

## 六、四个注意点

1. **已对真实 GKI 分支校验**。补丁在 `aosp-mirror/kernel_common` 的 `android16-6.12` 分支上
   `git apply --check` 返回 0；其中 `kernel/module/procfs.c` 与 `kernel/kallsyms.c` 两个文件
   与 `torvalds/linux v6.12` 上游**逐字节一致**，锚点不会漂。若你用的是 realme 另改过的 BSP 树
   （例如 `module_is_live()` 替代了 `mod->state == MODULE_STATE_UNFORMED`），`-F 3` 可能打不上
   ——那就按"方式 A"手改，一共三处、十来行。
2. **`m_show` 过滤是无条件的**。打上之后你自己 root 也查不到被藏模块，排查时把数组清空重编。
   要"只对非 su 可见"就别用这条路，改走 open_redirect（路线二）。
3. **改名单必须重编内核**。这是路线一让出去的唯一能力，动态改名单要加 supercall，
   会和 KernelSU 的 `CMD_SUSFS_*` 编号空间打架，不值得。
4. **内核态仍可见**。`m_show` 过滤的是输出层，`modules` 链表本身没动。
   自己的 LKM 或内核态取证照样能数出来——这一点和 LKM 版完全相同。

---

## 七、本机实测（RMX5200 / lafa，2026-11-14）

`qpace` 不是 Zygisk 用户态库，是**真内核模块**，由
`/data/adb/modules/hma_oss_zygisk/post-fs-data.sh` 用 `insmod` 加载：

```
/data/adb/modules/hma_oss_zygisk/qpace_drv.ko    → module name: qpace_drv
/data/adb/modules/hma_oss_zygisk/qpace_zram.ko   → module name: qpace_zram
```

名单已按实测填入。**但隐藏模块只解决三处，另有两处仍直接暴露 qpace**：

| 暴露面 | 当前内容 | 本补丁能否覆盖 |
|---|---|---|
| `/proc/modules` | `qpace_drv`、`qpace_zram` | ✅ `m_show()` 过滤 |
| `/proc/kallsyms` | 284 行带 `[qpace_zram]` / `[qpace_drv]` | ✅ `s_show()` 过滤 |
| `/sys/module/qpace_drv` `/sys/module/qpace_zram` | 两个目录 | ⚠️ 需 `ksu_susfs add_sus_path` |
| `/proc/crypto` | `name: qpace-lz4` / `driver: qpace-lz4-qcom` / `module: qpace_zram` | ❌ 需 open_redirect |
| `/sys/block/zram0/comp_algorithm` | `lzo lzo-rle lz4 zstd zstdn [qpace-lz4]` | ❌ 需 open_redirect |
| `getprop` | 无 qpace 痕迹 | 无需处理 |

### 补 `/sys/module`

```sh
ksu_susfs add_sus_path /sys/module/qpace_drv
ksu_susfs add_sus_path /sys/module/qpace_zram
```

### 补 `/proc/crypto` 与 `comp_algorithm`

模块加载完成后（`service.d` 阶段）生成替身，再挂重定向：

```sh
# 去掉含 qpace 的整段（/proc/crypto 以空行分段）
awk 'BEGIN{RS="";ORS="\n\n"} !/qpace/' /proc/crypto > /data/local/tmp/.crypto_fake

# 当前算法名回退成标准名
sed 's/qpace-lz4/lz4/' /sys/block/zram0/comp_algorithm > /data/local/tmp/.zram_alg

ksu_susfs config open_redirect add /proc/crypto /data/local/tmp/.crypto_fake 3
ksu_susfs config open_redirect add /sys/block/zram0/comp_algorithm /data/local/tmp/.zram_alg 3
```

`uid_scheme` 用 3（`UnmountedApp`，只骗 app 域），blast radius 最小：
`/proc/crypto` 有可能被某些 HAL 枚举，别用 2 把 root/系统进程一起骗了。

### 注意时序

`post-fs-data.sh` 就加载了 qpace，而 `service.d` 在它之后跑 —— 所以替身生成时
`/proc/crypto` 里已经有 qpace 条目，拿到的快照是对的。别把生成脚本挪到 `post-fs-data`。

---

## 八、运行时名单（后装的 ko 不用重编）

`/proc/oplus_mem_zone` —— **0600，仅 root**，用来在运行时增删名单，
和编译期数组取并集，改完立即生效（`m_show()` 每次读都重新比对）。

```sh
# 新增：后装的任何 ko，装完立刻登记，不用重编内核
echo "add zygisk_loader" > /proc/oplus_mem_zone

# 删除
echo "del zygisk_loader" > /proc/oplus_mem_zone

# 清空运行时表（编译期那两条不受影响）
echo clear > /proc/oplus_mem_zone

# 查看现状
cat /proc/oplus_mem_zone
# compiled: qpace_drv qpace_zram
# runtime (2/32):
```

实现要点：

| 项 | 值 |
|---|---|
| 容量 | `SUSFS_HIDE_MODULES_RT_MAX`，默认 32，可 `-D` 覆盖 |
| 并发 | `spin_lock_irqsave` 保护；`susfs_hide_module_name()` 在 `seq_file` 上下文里只持锁做 `strcmp`，不分配不睡眠 |
| 新名字生效时机 | 写入后**下一次读 `/proc/modules` 立刻生效**，无需重启 |
| 编译期开关 | 不想要这个节点就加 `-DSUSFS_HIDE_MODULES_NO_CTL`，只留编译期名单 |
| 节点本身 | root 才能看到内容；但节点存在性对 root 可见，属新增的极小暴露面 |

### 自动登记脚本

`service.d/99-hide-qpace.sh` 开机扫描 `/data/adb/modules` 下所有 `.ko`，
只登记**此刻真在内核里**的那些（避免同名厂商模块被误伤）：

```sh
for ko in $(find /data/adb/modules -name '*.ko' -type f 2>/dev/null); do
    n=$(basename "$ko" .ko | tr '-' '_')
    cut -d' ' -f1 /proc/modules | grep -qx "$n" && echo "add $n" > /proc/oplus_mem_zone
done
```

于是以后往 `/data/adb/modules` 里塞新模块，**重启后自动被抹**，内核一行都不用改。

已知窗口：`service.d` 在开机约 45 秒后才跑，这之前模块在 `/proc/modules` 里可见
（只有 root 域读得到，app 域本来就被 SELinux 挡住）。要更早只能把登记写进
`post-fs-data`，但那时 `/sys/block/zram0` 还没就绪，crypto/zram 那两步会失败。

---

## 九、接入 fastbuild workflow

补丁已直接写进 `fastbuild_6.12.23-susfs-hidden.yml` 和 `fastbuild_6.12.23-susfs-upstream.yml`，
位置在第 9 步（「应用 KernelSU & SUSFS 补丁」之后、「应用 lz4」之前）。

仓库里需要放一份：

```
susfs_hide_modules/0001-susfs-hide-modules.patch
```

（`fs/` 与 `include/` 两份源码已在补丁里，仓库里放不放都行，留着方便 review。）

### 为什么用 `git apply` 而不是 `patch`

实测 GNU patch 2.7.6（Ubuntu runner 同款）对**以空上下文行结尾的 hunk** 会报 `Hunk FAILED`，
即使上下文逐字节一致。所以步骤里优先 `git apply --whitespace=nowarn`，
失败才退回 `patch -p1 -F 3`；两条路都失败则整步 exit 1。

### 步骤里的四道闸

| 检查 | 拦的是什么 |
|---|---|
| `[ -f fs/susfs.c ]` + `grep -q susfs fs/Makefile` | susfs 主补丁那步带 `\|\| true`，静默失败时这里拦住 |
| `grep -q "susfs_hide_modules.o" fs/Makefile` | Makefile 那一 hunk 没落地 |
| `grep -q susfs_hide_module_name kernel/module/procfs.c` / `kernel/kallsyms.c` | 两个调用点没落地 |
| `grep -q qpace_drv fs/susfs_hide_modules.c` | 名单是占位符（等于没藏） |
