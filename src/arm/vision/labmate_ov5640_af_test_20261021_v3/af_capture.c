/* Same-stream OV5640 AF experiment for the ATK factory Linux driver. */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <poll.h>
#include <time.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>
#include <linux/v4l2-subdev.h>
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include "sources/ov5640_af_firmware.h"

static int video=-1, bus=-1, streaming=0, held=0, reset_original;
static enum v4l2_buf_type type=V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
static struct {void *p; size_t n;} buffers[8];
static unsigned count, width, height, stride, pixel;
static volatile sig_atomic_t interrupted;
static unsigned retry_total;
static int frame(int timeout,const char *path);
static void pause_ms(unsigned ms) {
    struct timespec t={.tv_sec=ms/1000,.tv_nsec=(ms%1000)*1000000L};
    while(nanosleep(&t,&t)<0 && errno==EINTR && !interrupted) {}
    if(interrupted) {errno=EINTR;fprintf(stderr,"Interrupted during I2C operation\n");exit(1);}
}
static void signal_stop(int sig) {(void)sig; interrupted=1;}
static int xio(int fd, unsigned long req, void *arg) {
    int r; do {r=ioctl(fd,req,arg);} while(r<0 && errno==EINTR && !interrupted); return r;
}
static void cleanup(void) {
    if(streaming) {xio(video,VIDIOC_STREAMOFF,&type); streaming=0;}
    for(unsigned i=0;i<count;i++) if(buffers[i].p && buffers[i].p!=MAP_FAILED) munmap(buffers[i].p,buffers[i].n);
    if(video>=0) close(video);
    if(bus>=0) close(bus);
}
static void fail(const char *s) {fprintf(stderr,"ERROR: %s (%s)\n",s,strerror(errno)); exit(1);}
static void check(int ok,const char *s) {if(!ok) {errno=EINVAL; fail(s);}}
static void i2c_transfer(struct i2c_rdwr_ioctl_data *d,unsigned reg,int val) {
    for(unsigned attempt=1;attempt<=11;attempt++) {
        int r=xio(bus,I2C_RDWR,d);
        if(r==(int)d->nmsgs) {pause_ms(1);return;}
        int saved=r<0?errno:EIO;
        if((saved==EBUSY || saved==EAGAIN) && attempt<11) {
            retry_total++;
            fprintf(stderr,"I2C_RETRY op=%s reg=0x%04x value=%d attempt=%u errno=%d (%s)\n",
                    val<0?"read":"write",reg,val,attempt,saved,strerror(saved));
            frame(0,NULL);pause_ms(20);continue;
        }
        fprintf(stderr,"I2C_FAILED op=%s reg=0x%04x value=%d msg_count=%u last_msg_bytes=%u attempts=%u result=%d errno=%d mcu_held=%d\n",
                val<0?"read":"write",reg,val,d->nmsgs,d->msgs[d->nmsgs-1].len,attempt,r,saved,held);
        errno=saved;fail("I2C transfer; no further AF commands will be issued");
    }
}
static int reg_read(unsigned reg) {
    uint8_t a[2]={reg>>8,reg},v;
    struct i2c_msg m[2]={{.addr=0x3c,.len=2,.buf=a},{.addr=0x3c,.flags=I2C_M_RD,.len=1,.buf=&v}};
    struct i2c_rdwr_ioctl_data d={.msgs=m,.nmsgs=2};
    i2c_transfer(&d,reg,-1);
    return v;
}
static void reg_write(unsigned reg,unsigned val) {
    uint8_t a[3]={reg>>8,reg,val};
    struct i2c_msg m={.addr=0x3c,.len=3,.buf=a};
    struct i2c_rdwr_ioctl_data d={.msgs=&m,.nmsgs=1};
    i2c_transfer(&d,reg,val);
}
/* OV5640 consecutive register access: 16-bit address, then payload bytes. */
static void reg_write_block(unsigned reg,const uint8_t *data,unsigned n) {
    uint8_t payload[130];
    check(n>0 && n<=128,"invalid firmware write block");
    payload[0]=reg>>8;payload[1]=reg;memcpy(payload+2,data,n);
    struct i2c_msg m={.addr=0x3c,.len=n+2,.buf=payload};
    struct i2c_rdwr_ioctl_data d={.msgs=&m,.nmsgs=1};
    i2c_transfer(&d,reg,data[0]);
}
static void reg_read_block(unsigned reg,uint8_t *data,unsigned n) {
    check(n>0 && n<=128,"invalid firmware read block");
    uint8_t address[2]={reg>>8,reg};
    struct i2c_msg m[2]={{.addr=0x3c,.len=2,.buf=address},
                       {.addr=0x3c,.flags=I2C_M_RD,.len=n,.buf=data}};
    struct i2c_rdwr_ioctl_data d={.msgs=m,.nmsgs=2};
    i2c_transfer(&d,reg,-1);
}
static long long millis(void) {struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return (long long)t.tv_sec*1000+t.tv_nsec/1000000;}
/* Dequeue/requeue during firmware upload and polling, not just at capture time. */
static int frame(int timeout,const char *path) {
    if(interrupted) {errno=EINTR; fail("interrupted");}
    struct pollfd p={.fd=video,.events=POLLIN};
    int r=poll(&p,1,timeout);
    if(r<0) fail("video poll");
    if(!r) return 0;
    struct v4l2_plane planes[VIDEO_MAX_PLANES]={0};
    struct v4l2_buffer b={.type=type,.memory=V4L2_MEMORY_MMAP,.length=VIDEO_MAX_PLANES,.m.planes=planes};
    if(xio(video,VIDIOC_DQBUF,&b)<0) {if(errno==EAGAIN) return 0; fail("DQBUF");}
    check(b.index<count && b.length==1,"unexpected video buffer");
    check(!(b.flags&V4L2_BUF_FLAG_ERROR),"video buffer error flag");
    if(path) {
        size_t off=planes[0].data_offset, need=(height-1)*stride+width*3;
        check(off<=buffers[b.index].n && need<=buffers[b.index].n-off,"short mapped frame");
        check(planes[0].bytesused>=off && need<=planes[0].bytesused-off,"short captured frame");
        FILE *f=fopen(path,"wb"); if(!f) fail("create PPM");
        fprintf(f,"P6\n%u %u\n255\n",width,height);
        uint8_t *src=(uint8_t*)buffers[b.index].p+off;
        uint8_t *row=malloc(width*3); if(!row) fail("allocate row");
        for(unsigned y=0;y<height;y++) {
            memcpy(row,src+y*stride,width*3);
            if(pixel==V4L2_PIX_FMT_BGR24) for(unsigned x=0;x<width;x++) {uint8_t t=row[x*3];row[x*3]=row[x*3+2];row[x*3+2]=t;}
            if(fwrite(row,1,width*3,f)!=width*3) fail("write PPM");
        }
        free(row); if(fclose(f)) fail("close PPM");
        printf("SAVED %s sequence=%u\n",path,b.sequence);
    }
    if(xio(video,VIDIOC_QBUF,&b)<0) fail("QBUF");
    return 1;
}
static void fresh(const char *path) {
    for(int i=0;i<10;i++) if(!frame(5000,NULL)) {errno=ETIMEDOUT;fail("settling frames");}
    if(!frame(5000,path)) {errno=ETIMEDOUT;fail("capture timeout");}
}
static void wait_register(unsigned reg,int value,int timeout) {
    long long end=millis()+timeout; int last=-1;
    do {
        int v=reg_read(reg);
        if(v!=last) {printf("REG %04x=%02x\n",reg,v); last=v;}
        if(v==value) return;
        frame(10,NULL);
    } while(millis()<end);
    errno=ETIMEDOUT;fail("AF register timeout (see last REG above)");
}
static void autofocus(void) {
    bus=open("/dev/i2c-2",O_RDWR); if(bus<0) fail("open i2c-2");
    int id=(reg_read(0x300a)<<8)|reg_read(0x300b);
    printf("SENSOR_ID=%04x\n",id);check(id==0x5640,"sensor ID mismatch; no AF writes performed");
    reset_original=reg_read(0x3000);reg_write(0x3000,reset_original|0x20);held=1;
    printf("AF_UPLOAD bytes=%zu mode=burst block=128\n",sizeof(ov5640_af_firmware));
    for(unsigned i=0;i<sizeof(ov5640_af_firmware);i+=128) {
        if(interrupted) {errno=EINTR;fail("AF upload interrupted");}
        unsigned n=sizeof(ov5640_af_firmware)-i;if(n>128)n=128;
        reg_write_block(0x8000+i,ov5640_af_firmware+i,n);
        printf("AF_UPLOAD_PROGRESS %u/%zu\n",i+n,sizeof(ov5640_af_firmware));
        frame(0,NULL);
    }
    for(unsigned i=0;i<sizeof(ov5640_af_firmware);i+=128) {
        uint8_t actual[128];
        unsigned n=sizeof(ov5640_af_firmware)-i;if(n>128)n=128;
        reg_read_block(0x8000+i,actual,n);
        for(unsigned j=0;j<n;j++) if(actual[j]!=ov5640_af_firmware[i+j]) {
            fprintf(stderr,"FW_MISMATCH reg=0x%04x expected=0x%02x actual=0x%02x\n",
                    0x8000+i+j,ov5640_af_firmware[i+j],actual[j]);
            check(0,"firmware readback mismatch; MCU remains held");
        }
        frame(0,NULL);
    }
    printf("AF_UPLOAD_VERIFIED retries=%u\n",retry_total);
    for(unsigned r=0x3022;r<=0x3028;r++) reg_write(r,0);
    reg_write(0x3029,0x7f);reg_write(0x3000,reset_original&~0x20);held=0;
    wait_register(0x3029,0x70,5000);
    reg_write(0x3023,1);reg_write(0x3022,3);
    wait_register(0x3023,0,10000);wait_register(0x3029,0x10,10000);
    puts("AF_REPORTED_COMPLETE (inspect the saved image for actual sharpness)");
    /* ATK-MC5640 manual, printed p.8: pause after single AF to hold focus. */
    reg_write(0x3023,1);reg_write(0x3022,0x06);
    wait_register(0x3023,0,3000);
    puts("AF_POSITION_HELD");
}
int main(int argc,char **argv) {
    if(argc!=2 || (strcmp(argv[1],"--capture-only") && strcmp(argv[1],"--autofocus"))) {
        fprintf(stderr,"Usage: af_capture --capture-only | --autofocus\nRun in an empty output directory. Fixed ATK /dev/video0, /dev/v4l-subdev0, i2c-2:003c.\n");return 2;
    }
    setvbuf(stdout,NULL,_IOLBF,0);atexit(cleanup);
    puts("AF_CAPTURE_VERSION=20261022_burst");
    signal(SIGINT,signal_stop);signal(SIGTERM,signal_stop);
    int sd=open("/dev/v4l-subdev0",O_RDWR);if(sd<0) fail("open subdevice");
    struct v4l2_subdev_format sf={.which=V4L2_SUBDEV_FORMAT_ACTIVE,.pad=0};
    if(xio(sd,VIDIOC_SUBDEV_G_FMT,&sf)<0) fail("subdevice G_FMT");
    sf.format.width=800;sf.format.height=480;sf.format.field=V4L2_FIELD_NONE;
    if(xio(sd,VIDIOC_SUBDEV_S_FMT,&sf)<0) fail("subdevice S_FMT");close(sd);
    check(sf.format.width==800 && sf.format.height==480,"sensor rejected dimensions");
    printf("SENSOR_FORMAT code=0x%x %ux%u\n",sf.format.code,sf.format.width,sf.format.height);
    video=open("/dev/video0",O_RDWR|O_NONBLOCK);if(video<0) fail("open video0");
    struct v4l2_capability cap={0};if(xio(video,VIDIOC_QUERYCAP,&cap)<0) fail("QUERYCAP");
    unsigned caps=(cap.capabilities&V4L2_CAP_DEVICE_CAPS)?cap.device_caps:cap.capabilities;
    check((caps&V4L2_CAP_VIDEO_CAPTURE_MPLANE) && (caps&V4L2_CAP_STREAMING),"need multiplanar streaming");
    struct v4l2_format fmt={.type=type};
    fmt.fmt.pix_mp.width=800;fmt.fmt.pix_mp.height=480;fmt.fmt.pix_mp.pixelformat=V4L2_PIX_FMT_RGB24;fmt.fmt.pix_mp.field=V4L2_FIELD_NONE;
    /* Factory xvip_dma_set_format preserves this caller-supplied field. */
    fmt.fmt.pix_mp.num_planes=1;
    fmt.fmt.pix_mp.plane_fmt[0].bytesperline=800*3;
    fmt.fmt.pix_mp.plane_fmt[0].sizeimage=800*480*3;
    if(xio(video,VIDIOC_S_FMT,&fmt)<0) fail("S_FMT");
    printf("S_FMT_RETURN %ux%u planes=%u stride=%u sizeimage=%u fourcc=0x%x\n",
           fmt.fmt.pix_mp.width,fmt.fmt.pix_mp.height,fmt.fmt.pix_mp.num_planes,
           fmt.fmt.pix_mp.plane_fmt[0].bytesperline,fmt.fmt.pix_mp.plane_fmt[0].sizeimage,fmt.fmt.pix_mp.pixelformat);
    memset(&fmt,0,sizeof(fmt));fmt.type=type;
    if(xio(video,VIDIOC_G_FMT,&fmt)<0) fail("G_FMT after S_FMT");
    width=fmt.fmt.pix_mp.width;height=fmt.fmt.pix_mp.height;pixel=fmt.fmt.pix_mp.pixelformat;stride=fmt.fmt.pix_mp.plane_fmt[0].bytesperline;
    printf("G_FMT_RETURN %ux%u planes=%u stride=%u sizeimage=%u fourcc=0x%x\n",
           width,height,fmt.fmt.pix_mp.num_planes,stride,fmt.fmt.pix_mp.plane_fmt[0].sizeimage,pixel);
    check(width==800 && height==480 && fmt.fmt.pix_mp.num_planes==1 && stride>=width*3 && (pixel==V4L2_PIX_FMT_RGB24 || pixel==V4L2_PIX_FMT_BGR24),"unexpected format/stride");
    printf("VIDEO_FORMAT %ux%u stride=%u fourcc=0x%x\n",width,height,stride,pixel);
    struct v4l2_requestbuffers req={.count=3,.type=type,.memory=V4L2_MEMORY_MMAP};
    if(xio(video,VIDIOC_REQBUFS,&req)<0) fail("REQBUFS");check(req.count>0 && req.count<=8,"buffer count"); count=req.count;
    for(unsigned i=0;i<count;i++) {
        struct v4l2_plane planes[VIDEO_MAX_PLANES]={0};
        struct v4l2_buffer b={.index=i,.type=type,.memory=V4L2_MEMORY_MMAP,.length=VIDEO_MAX_PLANES,.m.planes=planes};
        if(xio(video,VIDIOC_QUERYBUF,&b)<0) fail("QUERYBUF");check(b.length==1,"multiplane count");
        buffers[i].n=planes[0].length;buffers[i].p=mmap(NULL,buffers[i].n,PROT_READ|PROT_WRITE,MAP_SHARED,video,planes[0].m.mem_offset);
        if(buffers[i].p==MAP_FAILED) fail("mmap");if(xio(video,VIDIOC_QBUF,&b)<0) fail("initial QBUF");
    }
    if(xio(video,VIDIOC_STREAMON,&type)<0) fail("STREAMON");streaming=1;
    fresh("before.ppm");
    if(!strcmp(argv[1],"--autofocus")) {
        autofocus();fresh("after.ppm");
        reg_write(0x3023,1);reg_write(0x3022,0x08);
        wait_register(0x3023,0,3000);
        puts("AF_RELEASED_AFTER_CAPTURE");
    }
    puts("CAPTURE_COMPLETE");return 0;
}
