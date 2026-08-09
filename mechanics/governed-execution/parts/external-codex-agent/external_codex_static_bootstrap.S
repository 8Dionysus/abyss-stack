/*
 * Minimal x86_64 Linux bootstrap for installed external-actor wrappers.
 *
 * This ELF has no PT_INTERP and performs only direct syscalls.  It removes
 * every LD_* entry before the first dynamic executable is started, derives
 * <wrapper>.bootstrap.py from /proc/self/exe, and execs the fixed isolated
 * Python bootstrap while preserving all non-loader environment and user args.
 */

    .section .rodata
python_path:
    .asciz "/usr/bin/python3"
isolated_flag:
    .asciz "-I"
no_bytecode_flag:
    .asciz "-B"
proc_self_exe:
    .asciz "/proc/self/exe"
bootstrap_suffix:
    .ascii ".bootstrap.py"
bootstrap_suffix_end:

    .section .bss
    .align 16
executable_path:
    .skip 4096
new_argv:
    .skip 32768

    .section .text
    .global _start
    .type _start, @function
_start:
    movq %rsp, %r12
    movq (%r12), %r13
    cmpq $4090, %r13
    ja bootstrap_failure

    movq $89, %rax
    leaq proc_self_exe(%rip), %rdi
    leaq executable_path(%rip), %rsi
    movq $4000, %rdx
    syscall
    testq %rax, %rax
    jle bootstrap_failure

    movq %rax, %rdx
    leaq executable_path(%rip), %rdi
    addq %rdx, %rdi
    leaq bootstrap_suffix(%rip), %rsi
    movq $(bootstrap_suffix_end - bootstrap_suffix), %rcx
    addq %rcx, %rdx
    cmpq $4095, %rdx
    ja bootstrap_failure
    rep movsb
    movb $0, (%rdi)

    leaq new_argv(%rip), %r14
    leaq python_path(%rip), %rax
    movq %rax, 0(%r14)
    leaq isolated_flag(%rip), %rax
    movq %rax, 8(%r14)
    leaq no_bytecode_flag(%rip), %rax
    movq %rax, 16(%r14)
    leaq executable_path(%rip), %rax
    movq %rax, 24(%r14)

    movq $1, %rcx
copy_arguments:
    cmpq %r13, %rcx
    jae arguments_complete
    movq 8(%r12,%rcx,8), %rax
    movq %rax, 24(%r14,%rcx,8)
    incq %rcx
    jmp copy_arguments
arguments_complete:
    movq $0, 24(%r14,%rcx,8)

    leaq 16(%r12,%r13,8), %r15
    movq %r15, %rsi
    movq %r15, %rdi
filter_environment:
    movq (%rsi), %rax
    addq $8, %rsi
    testq %rax, %rax
    je environment_complete
    cmpb $'L', 0(%rax)
    jne keep_environment
    cmpb $'D', 1(%rax)
    jne keep_environment
    cmpb $'_', 2(%rax)
    je filter_environment
keep_environment:
    movq %rax, (%rdi)
    addq $8, %rdi
    jmp filter_environment
environment_complete:
    movq $0, (%rdi)

    movq $59, %rax
    leaq python_path(%rip), %rdi
    leaq new_argv(%rip), %rsi
    movq %r15, %rdx
    syscall

bootstrap_failure:
    movq $60, %rax
    movq $126, %rdi
    syscall

    .size _start, .-_start
    .section .note.GNU-stack,"",@progbits
