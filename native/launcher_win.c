/* Windows entry point for the portable build.
 *
 * Runs the bundled Python on the bundled application, passing the original
 * arguments through:  <exe dir>\runtime\python\python[w].exe -u -m re4pc ...
 * Built twice: RE4_CONSOLE=1 for re4mepc-cli.exe (waits, returns the exit
 * code), otherwise a GUI-subsystem re4mepc.exe that opens the launcher
 * without a console window.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

static const wchar_t *arguments_after_program(const wchar_t *line) {
    if (*line == L'"') {
        ++line;
        while (*line && *line != L'"') ++line;
        if (*line) ++line;
    } else {
        while (*line && *line != L' ' && *line != L'\t') ++line;
    }
    while (*line == L' ' || *line == L'\t') ++line;
    return line;
}

static void fail(const wchar_t *message) {
#ifdef RE4_CONSOLE
    fwprintf(stderr, L"re4mepc: %ls (error %lu)\n", message, GetLastError());
#else
    MessageBoxW(NULL, message, L"Resident Evil 4 Mobile PC Port", MB_ICONERROR | MB_OK);
#endif
}

static int run(void) {
    static wchar_t root[MAX_PATH], python[MAX_PATH], app[MAX_PATH], command[32768];
    DWORD length = GetModuleFileNameW(NULL, root, MAX_PATH);
    if (!length || length >= MAX_PATH) { fail(L"Cannot locate the application folder."); return 1; }
    wchar_t *slash = wcsrchr(root, L'\\');
    if (!slash) { fail(L"Cannot locate the application folder."); return 1; }
    *slash = 0;
#ifdef RE4_CONSOLE
    const wchar_t *interpreter = L"python.exe";
#else
    const wchar_t *interpreter = L"pythonw.exe";
#endif
    if (_snwprintf(python, MAX_PATH, L"%ls\\runtime\\python\\%ls", root, interpreter) < 0 ||
        _snwprintf(app, MAX_PATH, L"%ls\\runtime\\app", root) < 0) {
        fail(L"The application path is too long."); return 1;
    }
    if (GetFileAttributesW(python) == INVALID_FILE_ATTRIBUTES) {
        fail(L"The bundled Python runtime is missing. Extract the whole archive and run re4mepc.exe from it.");
        return 1;
    }
    SetEnvironmentVariableW(L"PYTHONPATH", app);
    SetEnvironmentVariableW(L"PYTHONHOME", NULL);
    SetEnvironmentVariableW(L"PYTHONNOUSERSITE", L"1");
    SetEnvironmentVariableW(L"PYTHONDONTWRITEBYTECODE", L"1");
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    const wchar_t *rest = arguments_after_program(GetCommandLineW());
    if (_snwprintf(command, 32768, L"\"%ls\" -u -m re4pc %ls", python, rest) < 0) {
        fail(L"The command line is too long."); return 1;
    }
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    startup.cb = sizeof(startup);
    /* Keep the caller's working directory so relative CLI paths still work. */
    if (!CreateProcessW(python, command, NULL, NULL, TRUE, 0, NULL, NULL, &startup, &process)) {
        fail(L"Cannot start the bundled Python runtime.");
        return 1;
    }
    DWORD code = 0;
#ifdef RE4_CONSOLE
    WaitForSingleObject(process.hProcess, INFINITE);
    GetExitCodeProcess(process.hProcess, &code);
#endif
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return (int)code;
}

#ifdef RE4_CONSOLE
int wmain(void) { return run(); }
#else
int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR line, int show) {
    (void)instance; (void)previous; (void)line; (void)show;
    return run();
}
#endif
