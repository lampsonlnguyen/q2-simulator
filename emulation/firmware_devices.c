/* Linux device boundary for the unmodified Q2 demo. No AWTK/UI hooks.
 * Build against the firmware libc; these declarations are the MIPS o32 ABI.
 */
typedef unsigned int u32;
typedef __SIZE_TYPE__ usize;
extern void *dlsym(void *, const char *);
extern int snprintf(char *, usize, const char *, ...);
extern long readlink(const char *, char *, usize);
extern int strcmp(const char *, const char *);
extern usize strlen(const char *);
extern void *memset(void *, int, usize);
extern void *memcpy(void *, const void *, usize);
extern int *__errno_location(void);
extern int open(const char *, int, ...);
extern int close(int);
extern long write(int, const void *, usize);
extern int usleep(unsigned int);

struct bitfield { u32 offset, length, msb_right; };
struct var_info {
    u32 xres, yres, xres_virtual, yres_virtual, xoffset, yoffset, bpp, grayscale;
    struct bitfield red, green, blue, transp;
    u32 nonstd, activate, height, width, accel_flags, pixclock;
    u32 left_margin, right_margin, upper_margin, lower_margin;
    u32 hsync_len, vsync_len, sync, vmode, rotate, colorspace, reserved[4];
};
struct fix_info {
    char id[16];
    u32 smem_start, smem_len, type, type_aux, visual;
    unsigned short xpanstep, ypanstep, ywrapstep;
    u32 line_length, mmio_start, mmio_len, accel;
    unsigned short capabilities, reserved[2];
};
static struct var_info mode = {
    .xres=320, .yres=375, .xres_virtual=320, .yres_virtual=1125, .bpp=32,
    .red={16,8,0}, .green={8,8,0}, .blue={0,8,0}, .transp={24,8,0},
    .height=~0u, .width=~0u,
};
static const struct fix_info fixed = {
    .id="q2-virtual-fb", .smem_len=320*375*4*3, .visual=2,
    .ypanstep=1, .line_length=320*4,
};
static u32 blank;
#ifndef Q2_DISPLAY_PATH
#define Q2_DISPLAY_PATH "/tmp/q2-hardware/display"
#endif
#ifdef __mips__
#define CREATE 0x100
#else
#define CREATE 0x40
#endif

static int device(int fd) {
    char path[64], target[4096];
    snprintf(path, sizeof path, "/proc/self/fd/%d", fd);
    long n=readlink(path, target, sizeof target-1);
    if (n<0) return 0;
    target[n]=0;
    usize len=(usize)n;
    if (len>=8 && !strcmp(target+len-8,"/dev/fb0")) return 1;
    if (len>=17) {
        const char *tail=target+len-17;
        if (!__builtin_memcmp(tail,"/dev/input/event",16) && tail[16]>='1' && tail[16]<='4')
            return tail[16]-'0'+1;
    }
    return 0;
}

static int unsupported(int kind, unsigned long request) {
    /* Record unknown requests rather than silently reporting device success. */
    char line[100];
    int n=snprintf(line,sizeof line,"q2-device: unsupported device=%d ioctl=0x%lx\n",kind,request);
    write(2,line,(usize)n);
    *__errno_location()=25; /* ENOTTY */
    return -1;
}

static void display_state(void) {
    /* yoffset, blank state; little-endian o32 words, read by the desktop. */
    u32 state[2]={mode.yoffset,blank};
    int fd=open(Q2_DISPLAY_PATH,1|CREATE,0600);
    if (fd>=0) { write(fd,state,sizeof state); close(fd); }
}

int ioctl(int fd, unsigned long request, ...) {
    __builtin_va_list ap;
    __builtin_va_start(ap,request);
    void *arg=__builtin_va_arg(ap,void *);
    __builtin_va_end(ap);
    int kind=device(fd);
    if (!kind) {
        int (*real)(int,unsigned long,...)=dlsym((void *)-1,"ioctl");
        return real(fd,request,arg);
    }
    if (kind==1) {
        if (request==0x4600) { memcpy(arg,&mode,sizeof mode); return 0; }
        if (request==0x4602) { memcpy(arg,&fixed,sizeof fixed); return 0; }
        if (request==0x4601 || request==0x4606) {
            struct var_info *v=arg;
            if (v->xres!=320 || v->yres!=375 || v->bpp!=32 || v->xoffset ||
                v->yoffset>750 || v->xres_virtual!=320 || v->yres_virtual!=1125) {
                *__errno_location()=22; return -1;
            }
            mode=*v; display_state(); return 0;
        }
        if (request==0x40044620) { usleep(16667); return 0; } /* FBIO_WAITFORVSYNC */
        if (request==0x4611) {
            if ((usize)arg>4) { *__errno_location()=22; return -1; }
            blank=(u32)(usize)arg;
            display_state();
            return 0;
        }
        return unsupported(kind,request);
    }
    unsigned nr=request&255, size=(request>>16)&8191;
    if (((request>>8)&255)!='E') return unsupported(kind,request);
    if (nr==1 && size==4) { *(u32 *)arg=0x10001; return 0; } /* EVIOCGVERSION */
    if (nr==2 && size==8) { memset(arg,0,size); return 0; } /* EVIOCGID */
    if (nr==6 && size) {
        const char *name=kind==2?"md-gpio-keys":kind==3?"q2-touch":"q2-wheel";
        return snprintf(arg,size,"%s",name)+1;
    }
    if (nr==0x20 && size) { /* EVIOCGBIT(0) */
        memset(arg,0,size); ((unsigned char *)arg)[0]=kind==2?3:11; return (int)size;
    }
    if (nr==0x21 && size) { /* EVIOCGBIT(EV_KEY) */
        memset(arg,0,size);
        unsigned keys[]={103,108,116,163,165,330};
        for (unsigned i=0;i<6;i++) {
            unsigned key=keys[i];
            if ((kind==2 ? i<5 : i==5) && key/8<size)
                ((unsigned char *)arg)[key/8]|=1u<<(key%8);
        }
        return (int)size;
    }
    if (nr==0x23 && size>=4) { /* EVIOCGBIT(EV_ABS) */
        memset(arg,0,size); *(u32 *)arg=(1u<<0)|(1u<<1)|(1u<<24); return (int)size;
    }
    if (nr>=0x40 && nr<=0x7f && size==24) { /* EVIOCGABS */
        u32 *a=arg;
        memset(arg,0,size);
        a[2]=nr==0x40 ? (kind==4?200:319) : nr==0x41?374:1;
        return 0;
    }
    if (request==0x80044590) return 0; /* EVIOCGRAB */
    return unsupported(kind,request);
}
