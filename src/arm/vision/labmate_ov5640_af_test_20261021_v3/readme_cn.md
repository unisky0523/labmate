# 官方手册流程：自动对焦后拍照保存（用户态）

日期：2026-10-22。版本 AF_CAPTURE_VERSION=20261022_burst。E 盘部署仍使用现有 labmate_ov5640_af_test_20261021_v3 目录，项目根目录新增 take_focused_photo.sh，避免继续生成版本文件夹。

## 本次做什么

使用原出厂内核、原视频驱动和 /dev/i2c-2。程序不写内核、设备树、BOOT.BIN、QSPI、eMMC 镜像，也不通过 /dev/mem 复位控制器。

主流程依据用户提供的《ATK-MC5640 模块用户手册》V1.1 第 2.6 节（印刷页 7–8，PDF 页 10–11）：

1. 打开同一次 800×480 RGB24 视频流，先保存 before.png。
2. 暂停 AF MCU，将候选固件从 0x8000 起下载，读回全部内容校验。
3. 启动 AF MCU，等候 FW_STATUS(0x3029)=0x70。
4. 写 CMD_MAIN(0x3022)=0x03，等待 FW_STATUS=0x10。
5. 写 CMD_MAIN=0x06，暂停并保持镜头位置；等待确认后丢弃旧帧并抓取新帧。
6. 保存 after.ppm / after.png / photo.jpg。原始帧保存后再用 0x08 释放镜头，结束采集。

固件下载和停止 MCU 的具体寄存器初始化参考现有 Espressif 实现；未使用手册未说明的主命令 0x01。控制命令使用 CMD_ACK 握手。

## 这次的关键变化

此前逐字节上传：4077 次写事务，读回也逐字节。本次每块至多 128 字节，从块首地址连续读写，上传 32 块、读回 32 块。目标是减少短事务数量；这是用户态传输方式的实验，并不保证能解决已有的 AXI IIC Busy 故障。

本次未取得正点原子配套例程中的 ov5640af.h。沿用现有 Espressif 官方仓库的 4077 字节候选固件，并非已验证的正点原子配套固件；具体来源见 sources/PROVENANCE.md。手册本身不包含固件字节。不要把“按官方手册流程”误读成已验证厂家固件适配。

连续写固件的方式参考 OpenMV 官方 OV5640 驱动和野火官方示例；128 字节分块及完整读回校验是本程序的移植选择，不是手册给定的分块参数。

## 在板卡执行

上次上传失败曾让 I2C 保持 Busy。首次测试前让板卡完整断电，再正常开机，以清理上次残留状态；不要在带电时插拔摄像头。

SD 卡在电脑安全弹出后插回板卡，在串口单独发送这一行：

```sh
sh /media/sd-mmcblk0p1/labmate_lite_image_reader_board_v2/take_focused_photo.sh
```

脚本会将新的三个运行文件复制到 /home/root/labmate_reader_v2/labmate_ov5640_af_test_20261021_v3，再运行 --autofocus。无需手工编译或更新板上旧副本。固定摄像头和纸上文字，保持光照和距离不变，等待命令结束。

正常日志应包含 AF_CAPTURE_VERSION=20261022_burst、AF_UPLOAD_PROGRESS 4077/4077、AF_UPLOAD_VERIFIED、AF_REPORTED_COMPLETE、AF_POSITION_HELD、PHOTO_SAVED=.../photo.jpg 和 NATIVE_EXIT=0。自动对焦状态完成后仍需检查实际照片清晰度。

每次结果保存在板上 OUTPUT= 后的独立 af_run_* 目录中，包含对焦前后图片、JPEG 照片、native.log 和报告。photo.jpg 对应对焦后抓取的帧，JPEG 质量设为 95。

若出现持续 I2C Busy，先把完整输出返回，不继续重复上传。本程序不会把失败的自动对焦结果标成成功，已经保存的 before.png 会保留。若后续释放镜头失败，已抓取的 after.ppm 仍会保留并转换；根据日志判断失败阶段。

## 图片复制回电脑

把实际 OUTPUT 目录中的 photo.jpg 复制到 SD：

```sh
cp /home/root/labmate_reader_v2/labmate_ov5640_af_test_20261021_v3/af_run_实际目录/photo.jpg /media/sd-mmcblk0p1/photo_af.jpg
cd "$HOME"
sync
umount /media/sd-mmcblk0p1
```

每条分别发送。卸载成功后拔卡，电脑上查看 E:/photo_af.jpg。

## 验证范围

交叉编译、出厂系统动态符号检查、Python 3.7 语法和脚本语法检查见 build/validation.txt。此版本尚未在实体板卡运行，不代表 Busy 已解决或自动对焦已验收。
