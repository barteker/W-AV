#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#define _USE_MATH_DEFINES
#include <math.h>
#include <pthread.h>
#include <alsa/asoundlib.h>
#include <SDL2/SDL.h>
#include <bcm2835.h>
#ifndef M_PI
#define M_PI (3.14159265358979323846)
#endif

// Configuration
#define SAMPLE_RATE 44100
#define CHANNELS 2
#define PERIOD_SIZE 1024
#define BUFFER_SIZE (PERIOD_SIZE * 4)
#define EQ_BANDS 7
#define ADC_CHANNELS 8  // 7 for EQ bands + 1 for volume
#define ADC_BITS 10     // 10-bit ADC resolution (0-1023)
#define SPI_CHANNEL 0   // SPI channel for ADC
#define DISPLAY_WIDTH 800
#define DISPLAY_HEIGHT 600

// ADC pins (for MCP3008 or similar)
// Update the SPI pin definitions to use hardware SPI on the Raspberry Pi 4B
// These are the correct hardware SPI0 pins for the Pi 4B
#define SPI_CS_PIN 5      // GPIO 5
#define SPI_MOSI_PIN 10   // GPIO 10 
#define SPI_MISO_PIN 9    // GPIO 9
#define SPI_CLK_PIN 11    // GPIO 11

// Equalizer parameters
typedef struct {
    float freq;      // Center frequency
    float gain;      // Gain in dB (-12 to +12)
    float q;         // Q factor (bandwidth)
    float a0, a1, a2, b0, b1, b2;  // Filter coefficients
    float x1[2], x2[2], y1[2], y2[2];  // Filter states for left and right channels
} EQ_Band;

// Audio processing state
typedef struct {
    snd_pcm_t *capture_handle;
    snd_pcm_t *playback_handle;
    EQ_Band eq_bands[EQ_BANDS];
    float volume;
    float *buffer;
    int buffer_size;
    int run;
    SDL_Window *window;
    SDL_Renderer *renderer;
    pthread_mutex_t mutex;
} AudioState;

// Function prototypes
int init_audio(AudioState *state);
int init_equalizer(AudioState *state);
int init_adc(void);
int init_display(AudioState *state);
void *audio_thread(void *arg);
void *display_thread(void *arg);
void *control_thread(void *arg);
void update_eq_coefficients(EQ_Band *band);
void process_audio(AudioState *state, float *buffer, int frames);
void cleanup(AudioState *state);
uint16_t read_adc_channel(int channel);

int main() {
    AudioState state;
    pthread_t audio_tid, display_tid, control_tid;
    
    // Initialize state
    memset(&state, 0, sizeof(AudioState));
    state.buffer_size = BUFFER_SIZE;
    state.buffer = (float *)malloc(state.buffer_size * CHANNELS * sizeof(float));
    state.volume = 1.0f;
    state.run = 1;
    pthread_mutex_init(&state.mutex, NULL);
    
    // Initialize components
    if (init_audio(&state) < 0) {
        fprintf(stderr, "Failed to initialize audio\n");
        cleanup(&state);
        return -1;
    }
    
    if (init_equalizer(&state) < 0) {
        fprintf(stderr, "Failed to initialize equalizer\n");
        cleanup(&state);
        return -1;
    }
    
    if (init_adc() < 0) {
        fprintf(stderr, "Failed to initialize ADC\n");
        cleanup(&state);
        return -1;
    }
    
    if (init_display(&state) < 0) {
        fprintf(stderr, "Failed to initialize display\n");
        cleanup(&state);
        return -1;
    }
    
    // Start threads
    pthread_create(&audio_tid, NULL, audio_thread, &state);
    pthread_create(&display_tid, NULL, display_thread, &state);
    pthread_create(&control_tid, NULL, control_thread, &state);
    
    // Wait for a key press to exit
    printf("Press Enter to exit...\n");
    getchar();
    
    // Cleanup
    state.run = 0;
    pthread_join(audio_tid, NULL);
    pthread_join(display_tid, NULL);
    pthread_join(control_tid, NULL);
    cleanup(&state);
    
    return 0;
}

// Update ALSA configuration to work better with Pi 4B
int init_audio(AudioState *state) {
    int err;
    snd_pcm_hw_params_t *hw_params;
    
    // Use "hw:0,0" for direct hardware access - more stable on Pi 4B
    if ((err = snd_pcm_open(&state->capture_handle, "hw:0,0", SND_PCM_STREAM_CAPTURE, 0)) < 0) {
        fprintf(stderr, "Cannot open capture device: %s\n", snd_strerror(err));
        return -1;
    }
    
    // Open playback device 
    if ((err = snd_pcm_open(&state->playback_handle, "hw:0,0", SND_PCM_STREAM_PLAYBACK, 0)) < 0) {
        fprintf(stderr, "Cannot open playback device: %s\n", snd_strerror(err));
        return -1;
    }
    
    // Configure capture
    snd_pcm_hw_params_alloca(&hw_params);
    snd_pcm_hw_params_any(state->capture_handle, hw_params);
    snd_pcm_hw_params_set_access(state->capture_handle, hw_params, SND_PCM_ACCESS_RW_INTERLEAVED);
    snd_pcm_hw_params_set_format(state->capture_handle, hw_params, SND_PCM_FORMAT_FLOAT_LE);
    snd_pcm_hw_params_set_channels(state->capture_handle, hw_params, CHANNELS);
    snd_pcm_hw_params_set_rate_near(state->capture_handle, hw_params, &(unsigned int){SAMPLE_RATE}, 0);
    snd_pcm_hw_params_set_buffer_size_near(state->capture_handle, hw_params, &(snd_pcm_uframes_t){BUFFER_SIZE});
    snd_pcm_hw_params_set_period_size_near(state->capture_handle, hw_params, &(snd_pcm_uframes_t){PERIOD_SIZE}, 0);
    
    if ((err = snd_pcm_hw_params(state->capture_handle, hw_params)) < 0) {
        fprintf(stderr, "Cannot set capture hardware parameters: %s\n", snd_strerror(err));
        return -1;
    }
    
    // Configure playback (same parameters)
    snd_pcm_hw_params_any(state->playback_handle, hw_params);
    snd_pcm_hw_params_set_access(state->playback_handle, hw_params, SND_PCM_ACCESS_RW_INTERLEAVED);
    snd_pcm_hw_params_set_format(state->playback_handle, hw_params, SND_PCM_FORMAT_FLOAT_LE);
    snd_pcm_hw_params_set_channels(state->playback_handle, hw_params, CHANNELS);
    snd_pcm_hw_params_set_rate_near(state->playback_handle, hw_params, &(unsigned int){SAMPLE_RATE}, 0);
    snd_pcm_hw_params_set_buffer_size_near(state->playback_handle, hw_params, &(snd_pcm_uframes_t){BUFFER_SIZE});
    snd_pcm_hw_params_set_period_size_near(state->playback_handle, hw_params, &(snd_pcm_uframes_t){PERIOD_SIZE}, 0);
    
    if ((err = snd_pcm_hw_params(state->playback_handle, hw_params)) < 0) {
        fprintf(stderr, "Cannot set playback hardware parameters: %s\n", snd_strerror(err));
        return -1;
    }
    
    // Prepare devices
    snd_pcm_prepare(state->capture_handle);
    snd_pcm_prepare(state->playback_handle);
    
    return 0;
}

int init_equalizer(AudioState *state) {
    // Initialize 7-band equalizer with typical frequencies
    float freqs[EQ_BANDS] = {63.0f, 250.0f, 500.0f, 1000.0f, 2000.0f, 4000.0f, 8000.0f};
    
    for (int i = 0; i < EQ_BANDS; i++) {
        state->eq_bands[i].freq = freqs[i];
        state->eq_bands[i].gain = 0.0f;  // Start with flat response
        state->eq_bands[i].q = 1.414f;   // Q = sqrt(2) for standard octave filter
        
        // Initialize filter states
        for (int ch = 0; ch < 2; ch++) {
            state->eq_bands[i].x1[ch] = 0.0f;
            state->eq_bands[i].x2[ch] = 0.0f;
            state->eq_bands[i].y1[ch] = 0.0f;
            state->eq_bands[i].y2[ch] = 0.0f;
        }
        
        // Calculate initial filter coefficients
        update_eq_coefficients(&state->eq_bands[i]);
    }
    
    return 0;
}

// Update the ADC initialization to use the hardware SPI properly on Pi 4B
int init_adc(void) {
    // Initialize BCM2835 library for GPIO access
    if (!bcm2835_init()) {
        fprintf(stderr, "Failed to initialize BCM2835 library\n");
        return -1;
    }
    
    // Initialize hardware SPI on Pi 4B (more reliable than bit-banging)
    bcm2835_spi_begin();
    
    // Configure SPI settings
    bcm2835_spi_setBitOrder(BCM2835_SPI_BIT_ORDER_MSBFIRST);
    bcm2835_spi_setDataMode(BCM2835_SPI_MODE0);
    bcm2835_spi_setClockDivider(BCM2835_SPI_CLOCK_DIVIDER_128); // 2MHz on Pi 4B
    
    // Use hardware chip select
    bcm2835_spi_chipSelect(BCM2835_SPI_CS0);
    bcm2835_spi_setChipSelectPolarity(BCM2835_SPI_CS0, LOW);
    
    return 0;
}

// Add this function to initialize the display specifically for Pi 4B dual HDMI
int init_display(AudioState *state) {
    // Initialize SDL for display
    if (SDL_Init(SDL_INIT_VIDEO) < 0) {
        fprintf(stderr, "SDL could not initialize! SDL_Error: %s\n", SDL_GetError());
        return -1;
    }
    
    // Set hint to use the second HDMI output on Pi 4B if available
    SDL_SetHint(SDL_HINT_VIDEODRIVER, "rpi");
    SDL_SetHint(SDL_HINT_VIDEO_HIGHDPI_DISABLED, "1");
    
    // For Pi 4B: Force the window to display on HDMI-1 (second output)
    char display_env[32];
    snprintf(display_env, sizeof(display_env), "DISPLAY=:0.%d", 1); // Use display 1 (second HDMI)
    putenv(display_env);
    
    // Create window (fullscreen for better performance)
    state->window = SDL_CreateWindow("Audio Oscilloscope", 
                                    SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED,
                                    DISPLAY_WIDTH, DISPLAY_HEIGHT, 
                                    SDL_WINDOW_SHOWN | SDL_WINDOW_FULLSCREEN_DESKTOP);
    
    if (state->window == NULL) {
        fprintf(stderr, "Window could not be created! SDL_Error: %s\n", SDL_GetError());
        SDL_Quit();
        return -1;
    }
    
    // Create hardware-accelerated renderer (important for Pi 4B performance)
    state->renderer = SDL_CreateRenderer(state->window, -1, 
                                        SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (state->renderer == NULL) {
        fprintf(stderr, "Renderer could not be created! SDL_Error: %s\n", SDL_GetError());
        SDL_DestroyWindow(state->window);
        SDL_Quit();
        return -1;
    }
    
    return 0;
}

void *audio_thread(void *arg) {
    AudioState *state = (AudioState *)arg;
    float buffer[PERIOD_SIZE * CHANNELS];
    
    while (state->run) {
        // Read audio data from capture device
        int frames = snd_pcm_readi(state->capture_handle, buffer, PERIOD_SIZE);
        
        if (frames < 0) {
            fprintf(stderr, "Read error: %s\n", snd_strerror(frames));
            snd_pcm_recover(state->capture_handle, frames, 0);
            continue;
        }
        
        // Process audio (apply EQ and volume)
        process_audio(state, buffer, frames);
        
        // Copy processed data to the display buffer
        pthread_mutex_lock(&state->mutex);
        memcpy(state->buffer, buffer, frames * CHANNELS * sizeof(float));
        pthread_mutex_unlock(&state->mutex);
        
        // Write processed audio to playback device
        int written = snd_pcm_writei(state->playback_handle, buffer, frames);
        
        if (written < 0) {
            fprintf(stderr, "Write error: %s\n", snd_strerror(written));
            snd_pcm_recover(state->playback_handle, written, 0);
        }
    }
    
    return NULL;
}

void *display_thread(void *arg) {
    AudioState *state = (AudioState *)arg;
    float buffer_copy[BUFFER_SIZE * CHANNELS];
    
    while (state->run) {
        // Copy buffer to avoid race conditions
        pthread_mutex_lock(&state->mutex);
        memcpy(buffer_copy, state->buffer, state->buffer_size * CHANNELS * sizeof(float));
        pthread_mutex_unlock(&state->mutex);
        
        // Clear screen
        SDL_SetRenderDrawColor(state->renderer, 0, 0, 0, 255);
        SDL_RenderClear(state->renderer);
        
        // Draw oscilloscope
        SDL_SetRenderDrawColor(state->renderer, 0, 255, 0, 255);
        
        // Draw waveform (left channel)
        for (int i = 0; i < DISPLAY_WIDTH - 1 && i < state->buffer_size - 1; i++) {
            // Scale and offset to fit in display
            int y1 = (DISPLAY_HEIGHT / 2) - (int)(buffer_copy[i * 2] * DISPLAY_HEIGHT / 4);
            int y2 = (DISPLAY_HEIGHT / 2) - (int)(buffer_copy[(i + 1) * 2] * DISPLAY_HEIGHT / 4);
            
            // Clamp values to screen
            y1 = (y1 < 0) ? 0 : (y1 >= DISPLAY_HEIGHT) ? DISPLAY_HEIGHT - 1 : y1;
            y2 = (y2 < 0) ? 0 : (y2 >= DISPLAY_HEIGHT) ? DISPLAY_HEIGHT - 1 : y2;
            
            // Draw line
            SDL_RenderDrawLine(state->renderer, i, y1, i + 1, y2);
        }
        
        // Draw waveform (right channel)
        SDL_SetRenderDrawColor(state->renderer, 0, 255, 255, 255);
        
        for (int i = 0; i < DISPLAY_WIDTH - 1 && i < state->buffer_size - 1; i++) {
            // Scale and offset to fit in display (offset from left channel)
            int y1 = (DISPLAY_HEIGHT / 2) - (int)(buffer_copy[i * 2 + 1] * DISPLAY_HEIGHT / 4);
            int y2 = (DISPLAY_HEIGHT / 2) - (int)(buffer_copy[(i + 1) * 2 + 1] * DISPLAY_HEIGHT / 4);
            
            // Clamp values to screen
            y1 = (y1 < 0) ? 0 : (y1 >= DISPLAY_HEIGHT) ? DISPLAY_HEIGHT - 1 : y1;
            y2 = (y2 < 0) ? 0 : (y2 >= DISPLAY_HEIGHT) ? DISPLAY_HEIGHT - 1 : y2;
            
            // Draw line
            SDL_RenderDrawLine(state->renderer, i, y1, i + 1, y2);
        }
        
        // Draw EQ levels
        for (int i = 0; i < EQ_BANDS; i++) {
            int x = (DISPLAY_WIDTH / (EQ_BANDS + 1)) * (i + 1);
            int height = (int)(state->eq_bands[i].gain * DISPLAY_HEIGHT / 24.0f); // Scale ±12dB to screen
            
            SDL_Rect eq_bar = {
                .x = x - 10,
                .y = (height >= 0) ? (DISPLAY_HEIGHT / 2) - height : (DISPLAY_HEIGHT / 2),
                .w = 20,
                .h = (height >= 0) ? height : -height
            };
            
            SDL_SetRenderDrawColor(state->renderer, 255, 165, 0, 255); // Orange
            SDL_RenderFillRect(state->renderer, &eq_bar);
        }
        
        // Draw volume level
        int vol_height = (int)(state->volume * DISPLAY_HEIGHT / 2.0f);
        SDL_Rect vol_bar = {
            .x = DISPLAY_WIDTH - 40,
            .y = DISPLAY_HEIGHT - vol_height,
            .w = 30,
            .h = vol_height
        };
        
        SDL_SetRenderDrawColor(state->renderer, 255, 50, 50, 255); // Red
        SDL_RenderFillRect(state->renderer, &vol_bar);
        
        // Draw center line
        SDL_SetRenderDrawColor(state->renderer, 100, 100, 100, 255);
        SDL_RenderDrawLine(state->renderer, 0, DISPLAY_HEIGHT / 2, DISPLAY_WIDTH, DISPLAY_HEIGHT / 2);
        
        // Update display
        SDL_RenderPresent(state->renderer);
        
        // Don't hog the CPU
        SDL_Delay(16); // ~60 FPS
    }
    
    return NULL;
}

void *control_thread(void *arg) {
    AudioState *state = (AudioState *)arg;
    int prev_values[ADC_CHANNELS] = {0};
    
    while (state->run) {
        // Read values from all ADC channels
        for (int i = 0; i < ADC_CHANNELS; i++) {
            uint16_t raw_value = read_adc_channel(i);
            
            // Apply some smoothing/debouncing (ignore small changes)
            if (abs(raw_value - prev_values[i]) > 5) {
                prev_values[i] = raw_value;
                
                if (i < EQ_BANDS) {
                    // EQ bands (convert from 0-1023 to -12dB to +12dB)
                    float gain = ((float)raw_value / (1 << ADC_BITS)) * 24.0f - 12.0f;
                    
                    // Update EQ band gain
                    pthread_mutex_lock(&state->mutex);
                    state->eq_bands[i].gain = gain;
                    update_eq_coefficients(&state->eq_bands[i]);
                    pthread_mutex_unlock(&state->mutex);
                    
                    printf("EQ Band %d: %.2f dB\n", i, gain);
                } else {
                    // Volume (convert from 0-1023 to 0-1)
                    float volume = (float)raw_value / (1 << ADC_BITS);
                    
                    // Update volume
                    pthread_mutex_lock(&state->mutex);
                    state->volume = volume;
                    pthread_mutex_unlock(&state->mutex);
                    
                    printf("Volume: %.2f\n", volume);
                }
            }
        }
        
        // Don't poll too fast to avoid hogging the CPU
        usleep(10000); // 10ms
    }
    
    return NULL;
}

void update_eq_coefficients(EQ_Band *band) {
    // Calculate biquad filter coefficients for a peaking EQ filter
    // Based on Audio EQ Cookbook by Robert Bristow-Johnson
    
    float omega = 2 * M_PI * band->freq / SAMPLE_RATE;
    float alpha = sin(omega) / (2 * band->q);
    float A = pow(10, band->gain / 40); // Convert dB to linear gain
    
    float cos_omega = cos(omega);
    
    // Calculate filter coefficients
    band->b0 = 1 + alpha * A;
    band->b1 = -2 * cos_omega;
    band->b2 = 1 - alpha * A;
    band->a0 = 1 + alpha / A;
    band->a1 = -2 * cos_omega;
    band->a2 = 1 - alpha / A;
    
    // Normalize by a0
    band->b0 /= band->a0;
    band->b1 /= band->a0;
    band->b2 /= band->a0;
    band->a1 /= band->a0;
    band->a2 /= band->a0;
}

// Update process_audio to fix unused parameter warnings

void process_audio(AudioState *state, float *buffer, int frames) {
    // Use NEON SIMD instructions if available on Pi 4B for better performance
    #ifdef __ARM_NEON
    // Even in the NEON placeholder, reference the parameters to avoid compiler warnings
    for (int f = 0; f < frames; f++) {
        float left_sample = buffer[f * 2];
        float right_sample = buffer[f * 2 + 1];
        
        // Simply apply volume in the placeholder (full EQ will be implemented later)
        buffer[f * 2] = left_sample * state->volume;
        buffer[f * 2 + 1] = right_sample * state->volume;
        
        // Apply clipping protection
        if (buffer[f * 2] > 1.0f) buffer[f * 2] = 1.0f;
        else if (buffer[f * 2] < -1.0f) buffer[f * 2] = -1.0f;
        
        if (buffer[f * 2 + 1] > 1.0f) buffer[f * 2 + 1] = 1.0f;
        else if (buffer[f * 2 + 1] < -1.0f) buffer[f * 2 + 1] = -1.0f;
    }
    #else
    // Original implementation remains the same
    for (int f = 0; f < frames; f++) {
        float left_sample = buffer[f * 2];
        float right_sample = buffer[f * 2 + 1];
        
        // Apply each EQ band in series
        for (int b = 0; b < EQ_BANDS; b++) {
            EQ_Band *band = &state->eq_bands[b];
            
            // Process left channel (Direct Form II)
            float left_in = left_sample - band->a1 * band->y1[0] - band->a2 * band->y2[0];
            float left_out = band->b0 * left_in + band->b1 * band->x1[0] + band->b2 * band->x2[0];
            
            // Update filter state (left)
            band->x2[0] = band->x1[0];
            band->x1[0] = left_in;
            band->y2[0] = band->y1[0];
            band->y1[0] = left_out;
            
            // Process right channel (Direct Form II)
            float right_in = right_sample - band->a1 * band->y1[1] - band->a2 * band->y2[1];
            float right_out = band->b0 * right_in + band->b1 * band->x1[1] + band->b2 * band->x2[1];
            
            // Update filter state (right)
            band->x2[1] = band->x1[1];
            band->x1[1] = right_in;
            band->y2[1] = band->y1[1];
            band->y1[1] = right_out;
            
            // Update samples for next band
            left_sample = left_out;
            right_sample = right_out;
        }
        
        // Apply volume
        buffer[f * 2] = left_sample * state->volume;
        buffer[f * 2 + 1] = right_sample * state->volume;
        
        // Apply clipping protection
        if (buffer[f * 2] > 1.0f) buffer[f * 2] = 1.0f;
        else if (buffer[f * 2] < -1.0f) buffer[f * 2] = -1.0f;
        
        if (buffer[f * 2 + 1] > 1.0f) buffer[f * 2 + 1] = 1.0f;
        else if (buffer[f * 2 + 1] < -1.0f) buffer[f * 2 + 1] = -1.0f;
    }
    #endif
}

// Replace the read_adc_channel function with this hardware SPI version for Pi 4B
uint16_t read_adc_channel(int channel) {
    uint8_t tx_buffer[3];
    uint8_t rx_buffer[3];
    
    // Prepare transmit buffer for MCP3008 protocol
    tx_buffer[0] = 0x01;                          // Start bit
    tx_buffer[1] = 0x80 | ((channel & 0x7) << 4); // Single-ended + channel
    tx_buffer[2] = 0x00;                          // Don't care
    
    // Use hardware SPI transfer - much more efficient on Pi 4B
    bcm2835_spi_transfernb((char*)tx_buffer, (char*)rx_buffer, 3);
    
    // Extract the 10-bit ADC value from the received data
    uint16_t result = ((rx_buffer[1] & 0x03) << 8) | rx_buffer[2];
    
    return result;
}

void cleanup(AudioState *state) {
    // Free allocated resources
    if (state->buffer) {
        free(state->buffer);
        state->buffer = NULL;
    }
    
    // Cleanup audio devices
    if (state->capture_handle) {
        snd_pcm_close(state->capture_handle);
        state->capture_handle = NULL;
    }
    
    if (state->playback_handle) {
        snd_pcm_close(state->playback_handle);
        state->playback_handle = NULL;
    }
    
    // Cleanup display
    if (state->renderer) {
        SDL_DestroyRenderer(state->renderer);
        state->renderer = NULL;
    }
    
    if (state->window) {
        SDL_DestroyWindow(state->window);
        state->window = NULL;
    }
    
    SDL_Quit();
    
    // Cleanup SPI/GPIO
    bcm2835_spi_end();
    bcm2835_close();
    
    // Cleanup mutex
    pthread_mutex_destroy(&state->mutex);
}