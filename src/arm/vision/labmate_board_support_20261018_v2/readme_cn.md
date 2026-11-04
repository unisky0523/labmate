# LabMate 板端离线补充包修正版 v2

日期：2026-10-18。适用于本次实际报告的 Zynq-7010、ARMv7 hard-float、CPython 3.7.6、glibc 2.30。

## 已准备的内容

| 文件 | 用途 | 本地验证 |
| --- | --- | --- |
| payload/smoke_infer | 用原 v2 源码重新交叉编译的推理入口 | ARMv7 hard-float；直接要求最高 GLIBC_2.4、GLIBCXX_3.4.21 |
| payload/libgomp.so.1 | 补齐 Paddle-Lite 的 OpenMP 运行库 | ARMv7 hard-float；要求最高 GLIBC_2.17，提供 GOMP_4.0 |
| payload/pyclipper/ | CPython 3.7 的 polygon offset 扩展 | 1.3.0.post5；ARMv7 hard-float，使用出厂 pyconfig 构建 |
| payload/native_fault.so | 仅对诊断子进程启用的故障地址采集器 | 记录信号、ARM PC/LR/SP 和进程内存映射 |
| board_support.py | 分阶段检查、备份安装、生成 OpenCV 诊断报告 | 仅使用 Python 标准库 |

v2 修复上一版 pyclipper 的 PyInit__pyclipper 初始化函数被隐藏的问题，并新增该函数必须在动态符号表中全局导出的检查。独立推理测试现在不再依赖 pyclipper 检查通过；安装仍要求两项都通过。OpenCV 诊断增加动态加载器的候选对象信息与 LD_DEBUG=files,reloc 日志。

这不是完整修复后的应用。尚未连接实体板执行测试，尚未修复 OpenCV 导入段错误。

交叉编译使用本机已有 Xilinx SDK 2018.3 的 ARM Linux GCC 7.3.1 和其较旧的 Linux sysroot，并非声称已取得当前出厂系统的精确 SDK。编译后额外把所有强动态导入符号与本地出厂 rootfs 的 glibc 2.30、libstdc++ 6.0.27、Python 3.7，以及原 Paddle-Lite 和补充 libgomp 的导出符号逐一核对，未发现缺失。完整结果在 STATIC_VALIDATION.json。静态检查不能代替板端运行与准确率验收。

## 转存到板卡

1. 在 Windows 解压同目录下的 labmate_board_support_20261018_v2.zip。
2. 把解压出的 labmate_board_support_20261018_v2 文件夹复制到 SD 卡根目录，安全弹出。
3. 在板端沿用已经确认的 SD 挂载点，将整个补充包复制到 HOME。不要在 FAT 分区直接运行。

以下仅以 /mnt/sd 为示例，实际不同需要替换；不会格式化或重新挂载分区：

```sh
cat /proc/mounts | grep mmc
cp -R /mnt/sd/labmate_board_support_20261018_v2 "$HOME/"
cd "$HOME/labmate_board_support_20261018_v2"
python3 board_support.py --app "$HOME/labmate_reader_v2" --install
```

若补充包同名目录已经存在，请使用新的独立目录保存此次解压内容，再在该目录执行脚本。

## 脚本做什么

1. 校验补充包 SHA-256，确认实际为 ARMv7 / Python 3.7。
2. 使用补充包目录下的文件测试动态依赖和 pyclipper 多边形运算。
3. 检查新 smoke_infer 能否加载，再运行 rec_input.f32 识别测试；它不依赖 OpenCV。
4. 只有识别输出形状与 rec_expected.json 相同、解码文本为 1.21V，并且原 Paddle-Lite 动态库哈希一致时，才执行 --install。
5. 在应用目录创建 support_backup_*，备份原 smoke_infer、已有 libgomp 和 pyclipper，再安装这三个组件到应用目录。不会替换 /lib、/usr/lib 的系统库，不需要 pip 或板上编译器。
6. 比对板上部分系统文件与出厂 rootfs 的哈希，并对 OpenCV 做动态加载和导入检查。诊断库只对两个 Python 子进程临时设置 LD_PRELOAD。
7. 输出 REPORT=.../report.txt。把这个文件完整回传即可，无需逐条手工收集日志。

安装会使原 board_manifest.json 中旧 smoke_infer 的哈希失效，这是预期的应用补丁；请保留补充包 PACKAGE_MANIFEST.json 和备份目录作为记录。

## 如何看结果

- recognition_sample_pass=True：独立识别测试形状和文本通过，仍不代表整图程序已经通过。
- installed=True：上述三个组件已经备份并安装到应用目录。
- opencv_import_pass=False：OpenCV 仍未修复；此时脚本退出码 2 是预期的未完成状态。请回传 report.txt，不要把它当成完整应用已修好。
- installed=False：查看报告中的依赖、pyclipper 或 recognition_sample 日志，脚本未完成安装。

如果 OpenCV 也通过，打开新终端后可以先执行：

```sh
cd "$HOME/labmate_reader_v2"
export LD_LIBRARY_PATH="$PWD${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
python3 -c 'import numpy, cv2, pyclipper; print(cv2.__version__)'
python3 -m c_vision_lite.board_reader --image sample.jpg --bundle "$PWD" --out runs_measure
```

首次如需较低内存流程探测可加 --detector-size 512；改变输入分辨率后须另行核对读数。

## 恢复旧程序

脚本会打印备份目录绝对路径。必要时可从该目录把 smoke_infer 复制回应用目录；不要误用其他历史备份。系统 libc 和加载器从未被此补充包修改。

## 仍待完成

OpenCV 必须继续依据这次报告定位：依赖能找到、导入仍段错误，不能简单判为少装一个包。报告包含崩溃 PC/LR 地址、内存映射、系统文件哈希，可以在电脑端结合原库分析，必要时重新编译匹配的 OpenCV Python 绑定。

SD 卡此前有 FAT 异常。保留电脑端源文件，转存后脚本会校验补充包；对卡本身的检查修复应在备份并卸载之后另行进行。
