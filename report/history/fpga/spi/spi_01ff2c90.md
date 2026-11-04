# Labmate SPI JPEG 协议 v1

Zynq 作主机，ESP32-WROOM 作从机。SPI mode1（CPOL0/CPHA1），8 位、MSB first、CS 低有效。所有字段是小端 uint32。每个数据块单独拉低一次 CS，用一个 Linux SPI_IOC_MESSAGE(1) 完成，不能把同一数据块拆成会松开 CS 的多次 write。

## 数据包

数据包固定 1056 字节：32 字节头 + 最多 1024 字节图片数据 + 补零。最后一包也固定长度，补零不计入 CRC。

| 字节偏移 | 字段 | 含义 |
|---|---|---|
| 0 | magic | 0x314A4D4C，线上的字节为 LMJ1 |
| 4 | frame_id | 当前图片帧号 |
| 8 | total_size | 完整 JPEG 字节数，4～65536 |
| 12 | offset | 本块在 JPEG 中的字节偏移 |
| 16 | payload_len | 本块有效字节数，1～1024 |
| 20 | frame_crc32 | 完整 JPEG 的 CRC32 |
| 24 | flags | FIRST=1、LAST=2，可组合；中间块为 0 |
| 28 | packet_crc32 | 对头的 0～27 字节及有效 payload 依次计算 CRC32 |
| 32 | payload | JPEG 数据；其后补零至 1056 字节 |

CRC 使用 IEEE CRC32 多项式 0xEDB88320，与 Python zlib.crc32 一致，seed=0。FIRST 必须 offset=0；后续 offset 必须连续。LAST 当且仅当 offset+payload_len=total_size，且接收端会检查整帧 CRC 和 JPEG 首尾标记。

## 确认事务

SPI 是同时收发，当前数据包对应的结果要在接收端处理之后才能取得。因此主机每发一个数据包，再发一个 **32 字节 POLL**：头格式相同、flags=4、payload_len=0、offset=0、packet_crc32 为前 28 字节 CRC。POLL 只读取状态，不修改当前图片状态。

ESP32 的 MISO 在每个事务开头给出上一已处理数据包的 ACK，主机忽略发数据时读到的旧 ACK，检查随后 POLL 读到的 ACK。

| 偏移 | ACK 字段 |
|---|---|
| 0 | 0x31414D4C，字节 LMA1 |
| 4 | frame_id |
| 8 | 已接收连续字节数 |
| 12 | status：0 当前块成功、1 完整 JPEG 成功、2 格式错误、3 包 CRC 错、4 顺序/标记错误、5 长度越界、6 整帧 CRC 错 |
| 16 | 当前帧声明的 frame_crc32 |
| 20、24 | 保留为 0 |
| 28 | ACK 前 28 字节的 CRC32 |

## READY 令牌

READY 是一根从 ESP32 到 Zynq 的 **翻转令牌线**，不是持续高电平表示可发送的普通握手。ESP32 启动时为 0；每次 SPI DMA 接收事务准备好时翻转一次。主机第一次等 1，发送后下一次等 0，再下一次等 1，以此类推。令牌变化后的电平保持到下一次准备事务，不要求 Linux 捕捉很短的脉冲。

一次数据包+POLL 正好两个事务，成功结束后下次图像发送从令牌 1 开始。仅允许一个发送进程。若发送中途异常终止，复位 ESP32 再开始；当前示例没有超时后的自动恢复或断点续传。每个事务等待令牌超时为 3 秒。

ESP32 用 DMA，收发缓冲区在 DMA 可访问内存中，长度均为 4 的倍数，主机事务只能为 1056 或 32 字节。ESP32 示例采用一个队列槽，便于确认内存生命周期和帧顺序。增加队列深度后需要重新设计 READY 和 ACK 次序，不能只改 queue_size。
