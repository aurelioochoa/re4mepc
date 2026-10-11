/* SDL audio mixer for decoded mobile game samples. */
#include <SDL.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define SLOTS 256
#define VOICES 32
struct sample { float *pcm; size_t count; int loop; float volume; };
struct voice { int active, paused, slot; size_t position; float volume; };
static struct sample samples[SLOTS];
static struct voice voices[VOICES];
static SDL_AudioDeviceID device;
static uint64_t output_frames, nonzero_samples;

static void mix(void *unused, Uint8 *stream, int length) {
    (void)unused;
    float *out = (float *)stream;
    size_t count = (size_t)length / sizeof(float);
    memset(stream, 0, (size_t)length);
    for (int v = 0; v < VOICES; ++v) {
        struct voice *voice = &voices[v];
        if (!voice->active || voice->paused) continue;
        struct sample *sample = &samples[voice->slot];
        if (!sample->pcm || !sample->count) { voice->active = 0; continue; }
        for (size_t i = 0; i < count; ++i) {
            if (voice->position >= sample->count) {
                if (sample->loop) voice->position = 0;
                else { voice->active = 0; break; }
            }
            out[i] += sample->pcm[voice->position++] * voice->volume * sample->volume;
        }
    }
    output_frames += count / 2;
    for (size_t i = 0; i < count; ++i) {
        if (out[i] != 0.f) nonzero_samples++;
        if (out[i] > 1.f) out[i] = 1.f;
        else if (out[i] < -1.f) out[i] = -1.f;
    }
}

int re4_audio_open(void) {
    if (device) return 0;
    if (SDL_InitSubSystem(SDL_INIT_AUDIO)) return -1;
    SDL_AudioSpec want = {0}, got;
    want.freq = 44100; want.format = AUDIO_F32SYS; want.channels = 2;
    want.samples = 1024; want.callback = mix;
    device = SDL_OpenAudioDevice(NULL, 0, &want, &got, 0);
    if (!device) return -1;
    SDL_PauseAudioDevice(device, 0);
    return 0;
}

int re4_audio_load(int slot, const void *data, size_t bytes, int loop) {
    if (slot < 0 || slot >= SLOTS || !device || !bytes || bytes % 8) return -1;
    float *copy = malloc(bytes);
    if (!copy) return -1;
    memcpy(copy, data, bytes);
    SDL_LockAudioDevice(device);
    for (int i = 0; i < VOICES; ++i) if (voices[i].slot == slot) voices[i].active = 0;
    free(samples[slot].pcm);
    samples[slot] = (struct sample){copy, bytes / sizeof(float), loop, 1.f};
    SDL_UnlockAudioDevice(device);
    return 0;
}

void re4_audio_play(int slot, float volume) {
    if (slot < 0 || slot >= SLOTS || !device || !samples[slot].pcm) return;
    SDL_LockAudioDevice(device);
    int target = -1;
    if (samples[slot].loop) {
        for (int i = 0; i < VOICES; ++i) if (voices[i].active && voices[i].slot == slot) { target = i; break; }
    }
    if (target < 0) for (int i = 0; i < VOICES; ++i) if (!voices[i].active) { target = i; break; }
    if (target < 0) target = VOICES - 1;
    voices[target] = (struct voice){1, 0, slot, 0, volume};
    SDL_UnlockAudioDevice(device);
}

void re4_audio_control(int slot, int operation, float volume) {
    if (slot < 0 || slot >= SLOTS || !device) return;
    SDL_LockAudioDevice(device);
    if (operation == 3) samples[slot].volume = volume;
    for (int i = 0; i < VOICES; ++i) if (voices[i].slot == slot) {
        if (operation == 0 || operation == 4) voices[i].active = 0;
        else if (operation == 1) voices[i].paused = 1;
        else if (operation == 2) voices[i].paused = 0;
    }
    if (operation == 4) { free(samples[slot].pcm); memset(&samples[slot], 0, sizeof(samples[slot])); }
    SDL_UnlockAudioDevice(device);
}

int re4_audio_playing(int slot) {
    if (!device) return 0;
    int result = 0;
    SDL_LockAudioDevice(device);
    for (int i = 0; i < VOICES; ++i) if (voices[i].slot == slot && voices[i].active) result = 1;
    SDL_UnlockAudioDevice(device);
    return result;
}

uint64_t re4_audio_measure(int nonzero) {
    if (device) SDL_LockAudioDevice(device);
    uint64_t result = nonzero ? nonzero_samples : output_frames;
    if (device) SDL_UnlockAudioDevice(device);
    return result;
}

void re4_audio_close(void) {
    if (device) SDL_CloseAudioDevice(device);
    device = 0;
    output_frames = nonzero_samples = 0;
    for (int i = 0; i < SLOTS; ++i) { free(samples[i].pcm); memset(&samples[i], 0, sizeof(samples[i])); }
    memset(voices, 0, sizeof(voices));
    SDL_QuitSubSystem(SDL_INIT_AUDIO);
}
