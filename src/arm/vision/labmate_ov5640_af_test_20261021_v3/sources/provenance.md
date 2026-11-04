# Provenance and scope

- User-provided ATK-MC5640 manual V1.1: D:/FPGA/ATK-MC5..V1.pdf, section 2.6, printed pp.7-8. Single AF command 0x03; completion status 0x10; hold command 0x06; release command 0x08; firmware readiness status 0x70.
- ALIENTEK's official tutorial confirms this command flow: https://www.cnblogs.com/zdyz/p/19052430 . It refers to an ov5640af.h firmware file, which was not obtained during this task.
- The firmware header is unchanged from the previously downloaded Espressif source: https://raw.githubusercontent.com/espressif/esp32-camera/master/sensors/private_include/ov5640_af_firmware.h . Prior firmware-file commit API record identifies 1d73d881bcecdd4149e7192b7fcf0dbd928169fd. The frozen header's SHA256 is recorded in the package manifest. This is a compatibility candidate; it must not be described as ALIENTEK's verified firmware.
- Espressif initialization reference: https://github.com/espressif/esp32-camera/blob/master/sensors/ov5640_af.c . Repository license: ESPRESSIF_LICENSE (Apache 2.0).
- Burst firmware write reference: OpenMV's official sensor driver https://github.com/openmv/openmv/blob/master/drivers/sensors/ov5640.c and EmbedFire's official example https://doc.embedfire.com/mcu/stm32/f429tiaozhanzhe/hal/zh/latest/doc/ov5640/ov5640.html . The 128-byte chunk size and block readback verification are local implementation choices, not instructions specified in the ATK manual.
- Official ALIENTEK GitHub repositories inspected: openedv/ATK-DNESP32S3-Board, openedv/ATK-DNESP32S3M-MiniBoard, openedv/M144Z-M4-Mini-Board-STM32F407, openedv/ATK-ESP32-Board-Framework. No matching standalone ov5640af.h was found in these inspected trees. The official legacy module download page returned HTTP 429. This does not prove that ALIENTEK does not provide a firmware download elsewhere.

No kernel modifications, controller MMIO writes, driver unbinding or flash writes are performed by this version.
