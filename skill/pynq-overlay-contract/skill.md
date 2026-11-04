---
name: pynq-overlay-contract
description: 在 PYNQ 加载 Overlay 前按可移植 JSON 契约核对 IP 实例、VLNV、AXI 地址窗和寄存器偏移。支持离线 ip_dict 快照和 PYNQ 元数据预检。
---

# PYNQ Overlay 契约预检

适用于具备 PYNQ 运行环境、配对 `.bit` 与 `.hwh` 的板卡和有 CPU 地址窗的 AXI 外设。实例路径、IP 型号和寄存器都由用户契约提供，换题或换板时更换契约及同一次构建的文件。若代码按 IP 实例访问且允许地址由 HWH 分配，可以省略绝对 `address` 字段。

## 运行

进入 `skill/pynq-overlay-contract/`。无板时，先用随包示例检查契约和 `Overlay.ip_dict` 快照。示例快照是人工构造的通用 AXI 外设数据。

```sh
python scripts/check_overlay.py examples/contract.example.json --snapshot examples/snapshot.example.json
```

在目标 PYNQ 环境中，把示例契约另存并按实际工程填写。`ip` 的键为 `ip_dict` 中的完整实例路径。`vlnv` 填 IP 类型标识，`min_range` 填软件所需地址窗大小（字节），可选 `address` 固定基地址，可选 `registers` 是需核对的 32 位对齐寄存器名与偏移。没有寄存器描述的 IP 可仅核对地址窗，寄存器语义另按 IP 文档确认。

```sh
python scripts/check_overlay.py my_contract.json --bit my_overlay.bit
```

脚本用 `Overlay(..., download=False)` 读取元数据，返回 JSON 与文件 SHA-256。匹配成功返回 0，缺 IP、类型或地址偏移不符、文件缺失则返回 1。文件哈希用来标识版本，配对关系以构建产物来源为准。[PYNQ Overlay API](https://pynq.readthedocs.io/en/latest/pynq_package/pynq.overlay.html)

## 上板核对

在空闲测试板上，预检通过后由操作者显式执行 Overlay 下载，检查 `is_loaded()`，再用应用已知、无读副作用的 ID 或状态寄存器确认硬件可达。IP 有 register_map 时用名称访问相应寄存器，否则按契约核对后的偏移使用 `read(offset)`。对清零型或弹出 FIFO 型寄存器，仅在测试协议要求时读取。不要只为核对元数据整组读取寄存器。

按现象区分三层问题。`.hwh` 找不到时核对同一次构建、同名配对。`ip_dict` 匹配但寄存器不可达时核对时钟、复位、AXI 地址路由和实际加载的 Overlay。寄存器可达但值不符时核对位域、访问权限和寄存器行为。脚本仅验证元数据和文件可用性，下载后的电气与运行状态在目标板核对。

## 来源、验证与失效条件

从 LabMate 接口迁移中提炼出「先审计硬件描述，再操作实际硬件」的检查方法。原项目部署使用厂商 Linux 和 spidev。这个 PYNQ 版本是通用扩展，板卡、AXI IP 和契约与语音或 SPI 应用无关。

已验证示例快照通过，缺 IP、错误地址窗和错误寄存器偏移被识别，并用模拟 Overlay 确认元数据读取传入 `download=False`。实体 PYNQ 板、真实 Overlay 下载、跨板复测尚未进行。它针对全量 `.bit` 配 `.hwh` 和单个 CPU 可见地址窗的基本场景。部分重配置、XRT 专用 `.xclbin`、多地址窗 IP 以及 DMA 缓存维护需要另设契约和验证流程。
