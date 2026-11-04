#define _GNU_SOURCE
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <ucontext.h>
#include <unistd.h>

/* Diagnostic child processes only. No allocation or stdio in the handler. */
static void literal(const char *text) {
    const char *end = text;
    while (*end) ++end;
    (void)write(2, text, (size_t)(end - text));
}

static void hexvalue(uintptr_t value) {
    char buffer[2 + sizeof(uintptr_t) * 2];
    static const char digits[] = "0123456789abcdef";
    buffer[0] = '0'; buffer[1] = 'x';
    for (unsigned i = 0; i < sizeof(uintptr_t) * 2; ++i) {
        unsigned shift = (sizeof(uintptr_t) * 2 - i - 1) * 4;
        buffer[i + 2] = digits[(value >> shift) & 15];
    }
    (void)write(2, buffer, sizeof(buffer));
}

/* Read through /proc so an invalid diagnostic pointer cannot fault again. */
static void linkmap_context(uintptr_t address) {
    int descriptor = open("/proc/self/mem", O_RDONLY);
    if (descriptor < 0) return;
    uint32_t words[40] = {0};
    ssize_t count = pread64(descriptor, words, sizeof(words), (off64_t)address);
    if (count >= 56) {
        literal("loader_candidate_address="); hexvalue(address);
        literal(" load_bias="); hexvalue(words[0]);
        literal(" dynamic="); hexvalue(words[2]);
        literal(" l_info_DT_STRTAB="); hexvalue(words[13]);
        literal("\nloader_candidate_name=");
        char name[512] = {0};
        ssize_t length = pread64(descriptor, name, sizeof(name) - 1, (off64_t)words[1]);
        if (length > 0) literal(name);
        literal("\nloader_candidate_words:");
        for (unsigned i = 0; i < 40 && i * 4 < (unsigned)count; ++i) {
            literal(" "); hexvalue(words[i]);
        }
        literal("\n");
    }
    close(descriptor);
}

static void handler(int number, siginfo_t *info, void *context) {
    ucontext_t *state = (ucontext_t *)context;
    literal("\nLABMATE_NATIVE_FAULT signal="); hexvalue((uintptr_t)number);
    literal(" addr="); hexvalue((uintptr_t)info->si_addr);
    literal(" pc="); hexvalue((uintptr_t)state->uc_mcontext.arm_pc);
    literal(" lr="); hexvalue((uintptr_t)state->uc_mcontext.arm_lr);
    literal(" sp="); hexvalue((uintptr_t)state->uc_mcontext.arm_sp);
    literal(" fp="); hexvalue((uintptr_t)state->uc_mcontext.arm_fp);
    literal("\n");
    linkmap_context((uintptr_t)state->uc_mcontext.arm_fp);
    literal("\n/proc/self/maps:\n");
    int descriptor = open("/proc/self/maps", O_RDONLY);
    if (descriptor >= 0) {
        char buffer[4096];
        ssize_t count;
        while ((count = read(descriptor, buffer, sizeof(buffer))) > 0)
            (void)write(2, buffer, (size_t)count);
        (void)close(descriptor);
    }
    _exit(128 + number);
}

__attribute__((constructor)) static void setup(void) {
    struct sigaction action = {0};
    action.sa_sigaction = handler;
    sigemptyset(&action.sa_mask);
    action.sa_flags = SA_SIGINFO | SA_RESETHAND;
    sigaction(SIGSEGV, &action, 0);
    sigaction(SIGBUS, &action, 0);
    sigaction(SIGILL, &action, 0);
    sigaction(SIGABRT, &action, 0);
}
