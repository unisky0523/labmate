/*
 * ov5640.c - OV5640 Camera Driver
 *
 * Copyright (C) 2019 Guangzhou Alientek Electronic Technology Co., Ltd.
 * Author: Deng Tao <773904075@qq.com>
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 */

#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/init.h>
#include <linux/module.h>
#include <linux/types.h>
#include <linux/of_device.h>
#include <linux/of_gpio.h>
#include <media/v4l2-device.h>
#include <media/v4l2-event.h>
#include <media/v4l2-subdev.h>

struct ov5640_dev {
	struct i2c_client *client;
	struct v4l2_subdev sd;
	struct media_pad pad;
	struct v4l2_mbus_framefmt fmt;
	struct gpio_desc *iprst_gpio;
	struct gpio_desc *rst_gpio;
	struct gpio_desc *pwdn_gpio;
};

struct ov5640_reg {
	u16 addr;
	u8 val;
};

static const struct ov5640_reg ov5640_global_init_setting[] = {
	{0x3008, 0x42}, {0x3103, 0x03}, {0x3017, 0xff},
	{0x3018, 0xff}, {0x3034, 0x1a}, {0x3037, 0x13},
	{0x3108, 0x01}, {0x3630, 0x36}, {0x3631, 0x0e},
	{0x3632, 0xe2}, {0x3633, 0x12}, {0x3621, 0xe0},
	{0x3704, 0xa0}, {0x3703, 0x5a}, {0x3715, 0x78},
	{0x3717, 0x01}, {0x370b, 0x60}, {0x3705, 0x1a},
	{0x3905, 0x02}, {0x3906, 0x10}, {0x3901, 0x0a},
	{0x3731, 0x12}, {0x3600, 0x08}, {0x3601, 0x33},
	{0x302d, 0x60}, {0x3620, 0x52}, {0x371b, 0x20},
	{0x471c, 0x50}, {0x3a13, 0x43}, {0x3a18, 0x00},
	{0x3a19, 0x7c}, {0x3635, 0x13}, {0x3636, 0x03},
	{0x3634, 0x40}, {0x3622, 0x01},

	//50/60Hz detection
	{0x3c01, 0x34}, // sum auto, band counter enable, threshold = 4
	{0x3c04, 0x28}, // threshold low sum
	{0x3c05, 0x98}, // threshold high sum
	{0x3c06, 0x00}, // light meter 1 threshold H
	{0x3c07, 0x07}, // light meter 1 threshold L
	{0x3c08, 0x00}, // light meter 2 threshold H
	{0x3c09, 0x1c}, // light meter 2 threshold L
	{0x3c0a, 0x9c}, // sample number H
	{0x3c0b, 0x40}, // sample number L
	{0x3810, 0x00}, // X offset
	{0x3811, 0x10}, // X offset
	{0x3812, 0x00}, // Y offset
	{0x3708, 0x64},
	{0x4001, 0x02}, // BLC start line
	{0x4005, 0x1a}, // BLC always update
	{0x3000, 0x00}, // enable MCU, OTP
	{0x3004, 0xff}, // enable BIST, MCU memory, MCU, OTP, STROBE, D5060, timing, array clock
	{0x300e, 0x58}, // MIPI 2 lane? power down PHY HS TX, PHY LP RX, DVP enable
	{0x302e, 0x00},
	{0x4300, 0x60}, // YUV 422, YUYV
	{0x501f, 0x01}, // ISP YUV 422
	{0x440e, 0x00},
	{0x5000, 0xa7}, // LENC on, raw gamma on, BPC on, WPC on, CIP on

	//AEC target
	{0x3a0f, 0x30}, // stable in high
	{0x3a10, 0x28}, // stable in low
	{0x3a1b, 0x30}, // stable out high
	{0x3a1e, 0x26}, // stable out low
	{0x3a11, 0x60}, // fast zone high
	{0x3a1f, 0x14}, // fast zone low

	//LENC
	{0x5800, 0x23}, {0x5801, 0x14}, {0x5802, 0x0f},
	{0x5803, 0x0f}, {0x5804, 0x12}, {0x5805, 0x26},
	{0x5806, 0x0c}, {0x5807, 0x08}, {0x5808, 0x05},
	{0x5809, 0x05}, {0x580a, 0x08}, {0x580b, 0x0d},
	{0x580c, 0x08}, {0x580d, 0x03}, {0x580e, 0x00},
	{0x580f, 0x00}, {0x5810, 0x03}, {0x5811, 0x09},
	{0x5812, 0x07}, {0x5813, 0x03}, {0x5814, 0x00},
	{0x5815, 0x01}, {0x5816, 0x03}, {0x5817, 0x08},
	{0x5818, 0x0d}, {0x5819, 0x08}, {0x581a, 0x05},
	{0x581b, 0x06}, {0x581c, 0x08}, {0x581d, 0x0e},
	{0x581e, 0x29}, {0x581f, 0x17}, {0x5820, 0x11},
	{0x5821, 0x11}, {0x5822, 0x15}, {0x5823, 0x28},
	{0x5824, 0x46}, {0x5825, 0x26}, {0x5826, 0x08},
	{0x5827, 0x26}, {0x5828, 0x64}, {0x5829, 0x26},
	{0x582a, 0x24}, {0x582b, 0x22}, {0x582c, 0x24},
	{0x582d, 0x24}, {0x582e, 0x06}, {0x582f, 0x22},
	{0x5830, 0x40}, {0x5831, 0x42}, {0x5832, 0x24},
	{0x5833, 0x26}, {0x5834, 0x24}, {0x5835, 0x22},
	{0x5836, 0x22}, {0x5837, 0x26}, {0x5838, 0x44},
	{0x5839, 0x24}, {0x583a, 0x26}, {0x583b, 0x28},
	{0x583c, 0x42}, {0x583d, 0xce}, // LENC BR offset

	//AWB
	{0x5180, 0xff}, // AWB B block
	{0x5181, 0xf2}, // AWB control
	{0x5182, 0x00}, // [7:4] max local counter, [3:0] max fast counter
	{0x5183, 0x14}, // AWB advance
	{0x5184, 0x25}, {0x5185, 0x24}, {0x5186, 0x09},
	{0x5187, 0x09}, {0x5188, 0x09}, {0x5189, 0x75},
	{0x518a, 0x54}, {0x518b, 0xe0}, {0x518c, 0xb2},
	{0x518d, 0x42}, {0x518e, 0x3d}, {0x518f, 0x56},
	{0x5190, 0x46},
	{0x5191, 0xf8}, // AWB top limit
	{0x5192, 0x04}, // AWB botton limit
	{0x5193, 0x70}, // Red limit
	{0x5194, 0xf0}, // Green Limit
	{0x5195, 0xf0}, // Blue limit
	{0x5196, 0x03}, // AWB control
	{0x5197, 0x01}, // local limit
	{0x5198, 0x04}, {0x5199, 0x12}, {0x519a, 0x04},
	{0x519b, 0x00}, {0x519c, 0x06}, {0x519d, 0x82},
	{0x519e, 0x38}, // AWB control

	//Gamma
	{0x5480, 0x01}, // BIAS plus on
	{0x5481, 0x08}, {0x5482, 0x14}, {0x5483, 0x28},
	{0x5484, 0x51}, {0x5485, 0x65}, {0x5486, 0x71},
	{0x5487, 0x7d}, {0x5488, 0x87}, {0x5489, 0x91},
	{0x548a, 0x9a}, {0x548b, 0xaa}, {0x548c, 0xb8},
	{0x548d, 0xcd}, {0x548e, 0xdd}, {0x548f, 0xea},
	{0x5490, 0x1d},

	//color matrix
	{0x5381, 0x1e}, // CMX1 for Y
	{0x5382, 0x5b}, // CMX2 for Y
	{0x5383, 0x08}, // CMX3 for Y
	{0x5384, 0x0a}, // CMX4 for U
	{0x5385, 0x7e}, // CMX5 for U
	{0x5386, 0x88}, // CMX6 for U
	{0x5387, 0x7c}, // CMX7 for V
	{0x5388, 0x6c}, // CMX8 for V
	{0x5389, 0x10}, // CMX9 for V
	{0x538a, 0x01}, // sign[9]
	{0x538b, 0x98}, // sign[8:1]

	//UV adjust
	{0x5580, 0x06}, // brightness on, saturation on
	{0x5583, 0x40}, // Sat U
	{0x5584, 0x10}, // Sat V
	{0x5589, 0x10}, // UV adjust th1
	{0x558a, 0x00}, // UV adjust th2[8]
	{0x558b, 0xf8}, // UV adjust th2[7:0]
	{0x501d, 0x40}, // enable manual offset in contrast

	//CIP
	{0x5300, 0x08}, // sharpen-MT th1
	{0x5301, 0x30}, // sharpen-MT th2
	{0x5302, 0x10}, // sharpen-MT off1
	{0x5303, 0x00}, // sharpen-MT off2
	{0x5304, 0x08}, // De-noise th1
	{0x5305, 0x30}, // De-noise th2
	{0x5306, 0x08}, // De-noise off1
	{0x5307, 0x16}, // De-noise off2
	{0x5309, 0x08}, // sharpen-TH th1
	{0x530a, 0x30}, // sharpen-TH th2
	{0x530b, 0x04}, // sharpen-TH off1
	{0x530c, 0x06}, // sharpen-TH off2
	{0x5025, 0x00},
	{0x3008, 0x02}, // wake up from software power down

	{0xFFFF, 0x00},
};

static const struct ov5640_reg ov5640_setting_480x272[] = {
	{0x3035, 0x21}, {0x3036, 0xa0}, {0x3c07, 0x08},
	{0x3820, 0x47}, {0x3821, 0x01}, {0x3814, 0x31},
	{0x3815, 0x31}, {0x3800, 0x00}, {0x3801, 0x00},
	{0x3802, 0x00}, {0x3803, 0x04}, {0x3804, 0x0a},
	{0x3805, 0x3f}, {0x3806, 0x07}, {0x3807, 0x9b},
	{0x3808, 0x01}, {0x3809, 0xe0}, {0x380a, 0x01},
	{0x380b, 0x10}, {0x380c, 0x07}, {0x380d, 0x68},
	{0x380e, 0x03}, {0x380f, 0xd8}, {0x3813, 0x06},
	{0x3618, 0x00}, {0x3612, 0x29}, {0x3709, 0x52},
	{0x370c, 0x03}, {0x3a02, 0x17}, {0x3a03, 0x10},
	{0x3a14, 0x17}, {0x3a15, 0x10}, {0x4004, 0x02},
	{0x3002, 0x1c}, {0x3006, 0xc3}, {0x4713, 0x03},
	{0x4407, 0x04}, {0x460b, 0x35}, {0x460c, 0x22},
	{0x4837, 0x22}, {0x3824, 0x02}, {0x5001, 0xa3},
	{0x3503, 0x00},
	{0xFFFF, 0x00},
};

static const struct ov5640_reg ov5640_setting_800x480[] = {
	{0x3035, 0x21}, {0x3036, 0xa0}, {0x3c07, 0x08},
	{0x3820, 0x43}, {0x3821, 0x01}, {0x3814, 0x31},
	{0x3815, 0x31}, {0x3800, 0x00}, {0x3801, 0x00},
	{0x3802, 0x00}, {0x3803, 0xbe}, {0x3804, 0x0a},
	{0x3805, 0x3f}, {0x3806, 0x06}, {0x3807, 0xe4},
	{0x3808, 0x03}, {0x3809, 0x20}, {0x380a, 0x01},
	{0x380b, 0xe0}, {0x380c, 0x07}, {0x380d, 0x69},
	{0x380e, 0x03}, {0x380f, 0x21}, {0x3813, 0x06},
	{0x3618, 0x00}, {0x3612, 0x29}, {0x3709, 0x52},
	{0x370c, 0x03}, {0x3a02, 0x09}, {0x3a03, 0x63},
	{0x3a14, 0x09}, {0x3a15, 0x63}, {0x4004, 0x02},
	{0x3002, 0x1c}, {0x3006, 0xc3}, {0x4713, 0x03},
	{0x4407, 0x04}, {0x460b, 0x35}, {0x460c, 0x22},
	{0x4837, 0x22}, {0x3824, 0x02}, {0x5001, 0xa3},
	{0x3503, 0x00},
	{0xFFFF, 0x00},
};

static const struct ov5640_reg ov5640_setting_1024x600[] = {
	{0x3035, 0x21}, {0x3036, 0xd0}, {0x3c07, 0x07},
	{0x3820, 0x47}, {0x3821, 0x01}, {0x3814, 0x31},
	{0x3815, 0x31}, {0x3800, 0x00}, {0x3801, 0x00},
	{0x3802, 0x00}, {0x3803, 0xfa}, {0x3804, 0x0a},
	{0x3805, 0x3f}, {0x3806, 0x06}, {0x3807, 0xa9},
	{0x3808, 0x04}, {0x3809, 0x00}, {0x380a, 0x02},
	{0x380b, 0x58}, {0x380c, 0x08}, {0x380d, 0x98},
	{0x380e, 0x03}, {0x380f, 0xe8}, {0x3813, 0x04},
	{0x3618, 0x00}, {0x3612, 0x29}, {0x3709, 0x52},
	{0x370c, 0x03}, {0x3a02, 0x08}, {0x3a03, 0xac},
	{0x3a14, 0x08}, {0x3a15, 0xac}, {0x4004, 0x02},
	{0x3002, 0x1c}, {0x3006, 0xc3}, {0x4713, 0x03},
	{0x4407, 0x04}, {0x460b, 0x37}, {0x460c, 0x22},
	{0x4837, 0x22}, {0x3824, 0x02}, {0x5001, 0xa3},
	{0x3503, 0x00},
	{0xFFFF, 0x00},
};

static const struct ov5640_reg ov5640_setting_1280x800[] = {
	{0x3035, 0x11}, {0x3036, 0xa0}, {0x3c07, 0x07},
	{0x3820, 0x47}, {0x3821, 0x01}, {0x3814, 0x31},
	{0x3815, 0x31}, {0x3800, 0x00}, {0x3801, 0x00},
	{0x3802, 0x00}, {0x3803, 0x04}, {0x3804, 0x0a},
	{0x3805, 0x3f}, {0x3806, 0x07}, {0x3807, 0x9b},
	{0x3808, 0x05}, {0x3809, 0x00}, {0x380a, 0x03},
	{0x380b, 0x20}, {0x380c, 0x0a}, {0x380d, 0x0a},
	{0x380e, 0x03}, {0x380f, 0xd4}, {0x3813, 0x06},
	{0x3618, 0x00}, {0x3612, 0x29}, {0x3709, 0x52},
	{0x370c, 0x03}, {0x3a02, 0x17}, {0x3a03, 0x10},
	{0x3a14, 0x17}, {0x3a15, 0x10}, {0x4004, 0x02},
	{0x3002, 0x1c}, {0x3006, 0xc3}, {0x4713, 0x03},
	{0x4407, 0x04}, {0x460b, 0x37}, {0x460c, 0x22},
	{0x4837, 0x22}, {0x3824, 0x02}, {0x5001, 0xa3},
	{0x3503, 0x00},
	{0xFFFF, 0x00},
};

static const struct ov5640_reg ov5640_setting_1920x1080[] = {
	{0x3035, 0x11}, {0x3036, 0x48}, {0x3c07, 0x07},
	{0x3820, 0x47}, {0x3821, 0x01}, {0x3814, 0x11},
	{0x3815, 0x11}, {0x3800, 0x00}, {0x3801, 0x00},
	{0x3802, 0x00}, {0x3803, 0x00}, {0x3804, 0x0a},
	{0x3805, 0x3f}, {0x3806, 0x07}, {0x3807, 0x9f},
	{0x3808, 0x07}, {0x3809, 0x80}, {0x380a, 0x04},
	{0x380b, 0x38}, {0x380c, 0x0b}, {0x380d, 0x1c},
	{0x380e, 0x07}, {0x380f, 0xb0}, {0x3813, 0x04},
	{0x3618, 0x04}, {0x3612, 0x29}, {0x3709, 0x12},
	{0x370c, 0x00}, {0x3a02, 0x03}, {0x3a03, 0xd8},
	{0x3a14, 0x03}, {0x3a15, 0xd8}, {0x4004, 0x06},
	{0x3002, 0x1c}, {0x3006, 0xc3}, {0x4713, 0x02},
	{0x4407, 0x0c}, {0x460b, 0x37}, {0x460c, 0x22},
	{0x4837, 0x2c}, {0x3824, 0x01}, {0x5001, 0x83},
	{0x3503, 0x00},
	{0xFFFF, 0x00},
};

static inline struct ov5640_dev *to_ov5640_dev(struct v4l2_subdev *sd)
{
	return container_of(sd, struct ov5640_dev, sd);
}

static void ov5640_power(struct ov5640_dev *sensor, bool enable)
{
	gpiod_set_value_cansleep(sensor->pwdn_gpio, enable ? 0 : 1);
}

static inline void ov5640_set_power_off(struct ov5640_dev *sensor)
{
	ov5640_power(sensor, false);
}

static void ov5640_reset(struct ov5640_dev *sensor)
{
	gpiod_set_value_cansleep(sensor->iprst_gpio, 0);
	usleep_range(5000, 10000);
	gpiod_set_value_cansleep(sensor->iprst_gpio, 1);
	usleep_range(5000, 10000);
	gpiod_set_value_cansleep(sensor->iprst_gpio, 0);
	usleep_range(5000, 10000);
	if (!sensor->rst_gpio)
		return;

	gpiod_set_value_cansleep(sensor->rst_gpio, 0);

	/* camera power cycle */
	ov5640_power(sensor, false);
	usleep_range(5000, 10000);
	ov5640_power(sensor, true);
	usleep_range(5000, 10000);

	gpiod_set_value_cansleep(sensor->rst_gpio, 1);
	usleep_range(1000, 2000);

	gpiod_set_value_cansleep(sensor->rst_gpio, 0);
	usleep_range(20000, 25000);
}

static void ov5640_set_power_on(struct ov5640_dev *sensor)
{
	ov5640_reset(sensor);
	ov5640_power(sensor, true);
}

static int ov5640_write_reg(struct ov5640_dev *ov5640, u16 addr, u8 val)
{
	struct i2c_client *client = ov5640->client;
	struct i2c_msg msg;
	u8 buf[3];
	int ret = -1;

	buf[0] = addr >> 8;		// high address
	buf[1] = addr & 0xff;	// low address
	buf[2] = val;

	msg.addr = client->addr;
	msg.flags = client->flags;
	msg.buf = buf;
	msg.len = sizeof(buf);

	ret = i2c_transfer(client->adapter, &msg, 1);
	if (1 != ret) {
		dev_err(&client->dev, "%s: error: addr=0x%x, val=0x%x\n",
				__func__, addr, val);
		return ret;
	}

	return 0;
}

static int ov5640_read_reg(struct ov5640_dev *ov5640, u16 addr, u8 *val)
{
	struct i2c_client *client = ov5640->client;
	struct i2c_msg msg[2];
	u8 buf[2];
	int ret = -1;

	buf[0] = addr >> 8;
	buf[1] = addr & 0xff;

	msg[0].addr = client->addr;
	msg[0].flags = client->flags;
	msg[0].buf = buf;
	msg[0].len = sizeof(buf);

	msg[1].addr = client->addr;
	msg[1].flags = client->flags | I2C_M_RD;
	msg[1].buf = buf;
	msg[1].len = 1;

	ret = i2c_transfer(client->adapter, msg, 2);
	if (2 != ret) {
		dev_err(&client->dev, "%s: error: addr=0x%x\n",
				__func__, addr);
		return ret;
	}

	*val = buf[0];
	return 0;
}

static int ov5640_read_reg16(struct ov5640_dev *ov5640, u16 addr, u16 *val)
{
	u8 hd, ld;
	int ret = -1;

	ret = ov5640_read_reg(ov5640, addr, &hd);
	if (ret)
		return ret;

	ret = ov5640_read_reg(ov5640, addr + 1, &ld);
	if (ret)
		return ret;

	*val = ((u16)hd << 8) | (u16)ld;
	return 0;
}

static int ov5640_check_chip_id(struct ov5640_dev *ov5640)
{
	struct i2c_client *client = ov5640->client;
	u16 chip_id;
	int ret = -1;

	ov5640_set_power_on(ov5640);

	ret = ov5640_read_reg16(ov5640, 0x300A, &chip_id);
	if (ret) {
		dev_err(&client->dev, "%s: failed to read chip identifier\n",
			__func__);
		goto power_off;
	}

	if (0x5640 != chip_id) {
		dev_err(&client->dev, "%s: Wrong chip identifier, expected 0x5640, got 0x%x\n",
				__func__, chip_id);
		ret = -ENXIO;
	}

	return ret;

power_off:
	ov5640_set_power_off(ov5640);
	return ret;
}

static int ov5640_s_power(struct v4l2_subdev *sd, int on)
{
	struct ov5640_dev *sensor = to_ov5640_dev(sd);

	if (on) 
		ov5640_set_power_on(sensor);
	else
		ov5640_set_power_off(sensor);

	return 0;
}

static int ov5640_s_stream(struct v4l2_subdev *sd, int enable)
{
	struct ov5640_dev *ov5640 = to_ov5640_dev(sd);
	struct v4l2_mbus_framefmt *mbus_fmt = &ov5640->fmt;
	int ret = -1;
	int i;

	if (enable) {
		ret = ov5640_write_reg(ov5640, 0x3103, 0x11);
		if (ret)
			return ret;
		ret = ov5640_write_reg(ov5640, 0x3008, 0x82);
		if (ret)
			return ret;
		msleep(10);

		for (i = 0; 0xFFFF != ov5640_global_init_setting[i].addr; i++) {
			ret = ov5640_write_reg(ov5640,
						ov5640_global_init_setting[i].addr,
						ov5640_global_init_setting[i].val);
			if (ret)
				return ret;
		}

		switch (mbus_fmt->width) {
		case 480:
			for (i = 0; 0xFFFF != ov5640_setting_480x272[i].addr; i++) {
				ret = ov5640_write_reg(ov5640,
							ov5640_setting_480x272[i].addr,
							ov5640_setting_480x272[i].val);
				if (ret)
					return ret;
				usleep_range(1000, 2000);
			}
		break;

		case 800:
			for (i = 0; 0xFFFF != ov5640_setting_800x480[i].addr; i++) {
				ret = ov5640_write_reg(ov5640,
							ov5640_setting_800x480[i].addr,
							ov5640_setting_800x480[i].val);
				if (ret)
					return ret;
				usleep_range(1000, 2000);
			}
		break;

		case 1024:
			for (i = 0; 0xFFFF != ov5640_setting_1024x600[i].addr; i++) {
				ret = ov5640_write_reg(ov5640,
							ov5640_setting_1024x600[i].addr,
							ov5640_setting_1024x600[i].val);
				if (ret)
					return ret;
				usleep_range(1000, 2000);
			}
		break;

		case 1280:
			for (i = 0; 0xFFFF != ov5640_setting_1280x800[i].addr; i++) {
				ret = ov5640_write_reg(ov5640,
							ov5640_setting_1280x800[i].addr,
							ov5640_setting_1280x800[i].val);
				if (ret)
					return ret;
				usleep_range(1000, 2000);
			}
		break;

		case 1920:
			for (i = 0; 0xFFFF != ov5640_setting_1920x1080[i].addr; i++) {
				ret = ov5640_write_reg(ov5640,
							ov5640_setting_1920x1080[i].addr,
							ov5640_setting_1920x1080[i].val);
				if (ret)
					return ret;
				usleep_range(500, 1000);
			}
		break;

		default:
		break;
		}
		// 测试闪光灯功能
		ov5640_write_reg(ov5640, 0x3016, 0x02);
		ov5640_write_reg(ov5640, 0x301c, 0x02);
		ov5640_write_reg(ov5640, 0x3019, 0x02); //打开闪光灯
		usleep_range(500, 1000);
		ov5640_write_reg(ov5640, 0x3019, 0x00); //关闭闪光灯
	}

	return 0;
}

static int ov5640_set_fmt(struct v4l2_subdev *sd,
			struct v4l2_subdev_pad_config *cfg,
			struct v4l2_subdev_format *format)
{
	struct ov5640_dev *ov5640 = to_ov5640_dev(sd);
	struct v4l2_mbus_framefmt *mbus_fmt = &format->format;

	ov5640->fmt.width = mbus_fmt->width;
	ov5640->fmt.height = mbus_fmt->height;
	return 0;
}

static int ov5640_get_fmt(struct v4l2_subdev *sd,
			  struct v4l2_subdev_pad_config *cfg,
			  struct v4l2_subdev_format *format)
{
	struct ov5640_dev *sensor = to_ov5640_dev(sd);
	struct v4l2_mbus_framefmt *fmt;

	if (format->pad != 0)
		return -EINVAL;

	if (format->which == V4L2_SUBDEV_FORMAT_TRY)
		fmt = v4l2_subdev_get_try_format(&sensor->sd, cfg,
						 format->pad);
	else
		fmt = &sensor->fmt;

	format->format = *fmt;
	return 0;
}

static struct v4l2_subdev_core_ops ov5640_subdev_core_ops = {
	.s_power = ov5640_s_power,
};

static struct v4l2_subdev_video_ops ov5640_subdev_video_ops = {
	.s_stream = ov5640_s_stream,
};

static const struct v4l2_subdev_pad_ops ov5640_subdev_pad_ops = {
	.set_fmt = ov5640_set_fmt,
	.get_fmt = ov5640_get_fmt,
};

static struct v4l2_subdev_ops ov5640_subdev_ops = {
	.core	= &ov5640_subdev_core_ops,
	.video	= &ov5640_subdev_video_ops,
	.pad	= &ov5640_subdev_pad_ops,
};

static int ov5640_probe(struct i2c_client *client)
{
	struct device *dev = &client->dev;
	struct ov5640_dev *ov5640 = NULL;
	struct v4l2_mbus_framefmt *fmt = NULL;
	int ret = -1;

	ov5640 = devm_kzalloc(dev, sizeof(struct ov5640_dev), GFP_KERNEL);
	if (!ov5640)
		return -ENOMEM;

	ov5640->client = client;

	/* request optional power down pin */
	ov5640->pwdn_gpio = devm_gpiod_get_optional(dev, "pwdn",
						    GPIOD_OUT_HIGH);
	if (IS_ERR(ov5640->pwdn_gpio)){
		dev_err(dev, "Failed to get pwdn-gpios\n");
		return PTR_ERR(ov5640->pwdn_gpio);
    }

	/* request optional reset pin */
	ov5640->rst_gpio = devm_gpiod_get_optional(dev, "reset",
						     GPIOD_OUT_HIGH);
	if (IS_ERR(ov5640->rst_gpio)) {
		dev_err(dev, "Failed to get reset-gpios\n");
		return PTR_ERR(ov5640->rst_gpio);
    }

	//TODO
	ov5640->iprst_gpio = devm_gpiod_get_optional(dev, "iprst",
						     GPIOD_OUT_HIGH);
	if (IS_ERR(ov5640->iprst_gpio)) {
		dev_err(dev, "Failed to get iprst_gpio-gpios\n");
		return PTR_ERR(ov5640->iprst_gpio);
    }

	/* Check ov5640 sensor ID */
	ret = ov5640_check_chip_id(ov5640);
	if (ret)
		return ret;

	/* default init sequence initialize sensor */
	fmt = &ov5640->fmt;
	fmt->code = MEDIA_BUS_FMT_RBG888_1X24; //MEDIA_BUS_FMT_RGB565_2X8_BE;
	fmt->colorspace = V4L2_COLORSPACE_SRGB;
	fmt->width = 800;
	fmt->height = 480;
	fmt->field = V4L2_FIELD_NONE;

	/* Initialize subdev */
	v4l2_i2c_subdev_init(&ov5640->sd, client, &ov5640_subdev_ops);

	/* Initialize media entity pad */
	ov5640->sd.flags |= V4L2_SUBDEV_FL_HAS_DEVNODE |
			    V4L2_SUBDEV_FL_HAS_EVENTS;;
	ov5640->sd.entity.function = MEDIA_ENT_F_CAM_SENSOR;
	ov5640->pad.flags = MEDIA_PAD_FL_SOURCE;
	ret = media_entity_pads_init(&ov5640->sd.entity, 1, &ov5640->pad);
	if (ret)
		return ret;

	/* Register v4l2 subdev */
	ret = v4l2_async_register_subdev_sensor_common(&ov5640->sd);
	if (ret)
		goto entity_cleanup;

	dev_info(dev, "Device registration is successful!\n");
	return 0;

entity_cleanup:
	media_entity_cleanup(&ov5640->sd.entity);
	return ret;
}

static int ov5640_remove(struct i2c_client *client)
{
	struct ov5640_dev *ov5640 = i2c_get_clientdata(client);

	ov5640_set_power_off(ov5640);
	v4l2_async_unregister_subdev(&ov5640->sd);
	media_entity_cleanup(&ov5640->sd.entity);
	return 0;
}

static const struct i2c_device_id ov5640_id[] = {
	{"ov5640", 0},
	{},
};
MODULE_DEVICE_TABLE(i2c, ov5640_id);

static const struct of_device_id ov5640_dt_ids[] = {
	{ .compatible = "ovti,ov5640" },
	{ /* sentinel */ },
};
MODULE_DEVICE_TABLE(of, ov5640_dt_ids);

static struct i2c_driver ov5640_i2c_driver = {
	.driver = {
		.name = "ov5640",
		.of_match_table = ov5640_dt_ids,
	},
	.id_table = ov5640_id,
	.probe_new = ov5640_probe,
	.remove   = ov5640_remove,
};

module_i2c_driver(ov5640_i2c_driver);

MODULE_AUTHOR("Deng Tao <773904075@qq.com>, Alientek, Inc.");
MODULE_DESCRIPTION("OV5640 Camera Driver");
MODULE_LICENSE("GPL v2");
MODULE_VERSION("1.0");
