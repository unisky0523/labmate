echo SPI_PERMANENT_BOOT_20261104
if ext4load mmc 1:1 0x02000000 /boot/spi-20261104/zImage; then
    if ext4load mmc 1:1 0x01f00000 /boot/spi-20261104/system-spi.dtb; then
        if ext4load mmc 1:1 0x04000000 /boot/spi-20261104/asr_esp32_spi.bit; then
            if fpga loadb 0 0x04000000 ${filesize}; then
                mw.l 0xf8000008 0x0000df0d
                mw.l 0xf8000900 0x0000000f
                mw.l 0xf8000240 0x00000000
                mw.l 0xf8000158 0x00000601
                mw.l 0xf800012c 0x01fd4ccd
                mw.l 0xf8000004 0x0000767b
                fdt addr 0x01f00000
                fdt resize 0x1000
                fdt set /amba/ethernet@e000b000 local-mac-address [00 0a 35 00 c0 13]
                fdt mknode / chipid
                fdt set /chipid chipid 7z010
                setenv bootargs earlycon console=ttyPS0,115200 cma=50M root=/dev/mmcblk1p1 rw rootwait
                echo SPI_EMMC_BOOT_READY
                bootz 0x02000000 - 0x01f00000
            fi
        fi
    fi
fi
echo SPI_BOOT_FAILED_FALLBACK_FACTORY_IMAGE
if sf probe 0 0 0; then
    if sf read 0x10000000 0x620000 0x700000; then
        bootm 0x10000000#config-7010
    fi
fi
echo BOOT_FAILED_USE_UBOOT_RECOVERY
