<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { recordPlay, updateProgress } from '@/api/videos'

interface Props {
  videoId: number
  videoUrl: string
  autoplay?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  autoplay: false,
})

const emit = defineEmits<{
  (e: 'play'): void
  (e: 'pause'): void
  (e: 'ended'): void
  (e: 'error', error: Event): void
}>()

const videoRef = ref<HTMLVideoElement>()
const playerRef = ref<HTMLDivElement>()
const isPlaying = ref(false)
const showControls = ref(true)
const currentTime = ref(0)
const duration = ref(0)
const progress = ref(0)
const volume = ref(1)
const isMuted = ref(false)
const isFullscreen = ref(false)
const loading = ref(true)
const hasError = ref(false)
const errorMessage = ref('')

let controlsTimeout: ReturnType<typeof setTimeout> | null = null
let progressInterval: ReturnType<typeof setInterval> | null = null
let hasRecordedPlay = false

function togglePlay() {
  if (!videoRef.value) return
  if (isPlaying.value) {
    videoRef.value.pause()
  } else {
    videoRef.value.play().catch((err) => {
      console.error('Playback failed:', err)
      hasError.value = true
      errorMessage.value = '播放失败'
    })
  }
}

function handleTimeUpdate() {
  if (!videoRef.value) return
  currentTime.value = videoRef.value.currentTime
  progress.value = duration.value > 0 ? (currentTime.value / duration.value) * 100 : 0
}

function handleMetadata() {
  if (!videoRef.value) return
  duration.value = videoRef.value.duration
  loading.value = false
}

function handlePlay() {
  isPlaying.value = true
  emit('play')
  // Record play on first play
  if (!hasRecordedPlay && props.videoId) {
    hasRecordedPlay = true
    recordPlay(props.videoId).catch(console.error)
  }
}

function handlePause() {
  isPlaying.value = false
  emit('pause')
}

function handleEnded() {
  isPlaying.value = false
  hasRecordedPlay = false
  emit('ended')
}

function handleLoadStart() {
  loading.value = true
  hasError.value = false
  errorMessage.value = ''
}

function handleLoadedData() {
  loading.value = false
}

function handleError(e: Event) {
  loading.value = false
  hasError.value = true
  errorMessage.value = '视频加载失败'
  emit('error', e)
}

function seek(e: MouseEvent) {
  if (!videoRef.value || !playerRef.value) return
  const rect = playerRef.value.getBoundingClientRect()
  const percent = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  videoRef.value.currentTime = percent * duration.value
}

function handleSeekbarHover(_e: MouseEvent) {
  // Could show seek preview tooltip here
}

function setVolume(e: MouseEvent) {
  if (!videoRef.value) return
  const rect = (e.target as HTMLElement).getBoundingClientRect()
  const percent = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  volume.value = percent
  videoRef.value.volume = percent
  isMuted.value = percent === 0
}

function toggleMute() {
  if (!videoRef.value) return
  if (isMuted.value) {
    videoRef.value.volume = volume.value || 0.5
    videoRef.value.muted = false
    isMuted.value = false
  } else {
    videoRef.value.muted = true
    isMuted.value = true
  }
}

function toggleFullscreen() {
  if (!playerRef.value) return
  if (document.fullscreenElement) {
    document.exitFullscreen()
    isFullscreen.value = false
  } else {
    playerRef.value.requestFullscreen()
    isFullscreen.value = true
  }
}

function handleFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}

function skipForward(seconds: number = 10) {
  if (!videoRef.value) return
  videoRef.value.currentTime = Math.min(videoRef.value.duration, videoRef.value.currentTime + seconds)
}

function skipBackward(seconds: number = 10) {
  if (!videoRef.value) return
  videoRef.value.currentTime = Math.max(0, videoRef.value.currentTime - seconds)
}

function formatTime(seconds: number): string {
  if (!isFinite(seconds)) return '0:00'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  return `${m}:${String(s).padStart(2, '0')}`
}

function showControlsTemporarily() {
  showControls.value = true
  if (controlsTimeout) {
    clearTimeout(controlsTimeout)
  }
  controlsTimeout = setTimeout(() => {
    if (isPlaying.value) {
      showControls.value = false
    }
  }, 3000)
}

function handleMouseMove() {
  showControlsTemporarily()
}

function startProgressReporting() {
  progressInterval = setInterval(async () => {
    if (isPlaying.value && props.videoId && currentTime.value > 0) {
      await updateProgress(props.videoId, Math.floor(currentTime.value)).catch(console.error)
    }
  }, 30000) // Report every 30 seconds
}

// Keyboard shortcuts
function handleKeydown(e: KeyboardEvent) {
  if (!videoRef.value) return

  switch (e.key) {
    case ' ':
    case 'k':
      e.preventDefault()
      togglePlay()
      break
    case 'ArrowLeft':
      e.preventDefault()
      skipBackward(5)
      break
    case 'ArrowRight':
      e.preventDefault()
      skipForward(5)
      break
    case 'ArrowUp':
      e.preventDefault()
      volume.value = Math.min(1, volume.value + 0.1)
      videoRef.value.volume = volume.value
      break
    case 'ArrowDown':
      e.preventDefault()
      volume.value = Math.max(0, volume.value - 0.1)
      videoRef.value.volume = volume.value
      break
    case 'm':
      e.preventDefault()
      toggleMute()
      break
    case 'f':
      e.preventDefault()
      toggleFullscreen()
      break
  }
}

onMounted(() => {
  startProgressReporting()
  document.addEventListener('fullscreenchange', handleFullscreenChange)
  document.addEventListener('keydown', handleKeydown)
  showControlsTemporarily()
})

onUnmounted(() => {
  if (progressInterval) {
    clearInterval(progressInterval)
  }
  if (controlsTimeout) {
    clearTimeout(controlsTimeout)
  }
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
  document.removeEventListener('keydown', handleKeydown)

  // Report final progress
  if (props.videoId && currentTime.value > 0) {
    updateProgress(props.videoId, Math.floor(currentTime.value)).catch(console.error)
  }
})

watch(() => props.videoId, () => {
  hasRecordedPlay = false
  currentTime.value = 0
  duration.value = 0
  progress.value = 0
  loading.value = true
  hasError.value = false
})
</script>

<template>
  <div
    ref="playerRef"
    class="video-player"
    @mousemove="handleMouseMove"
    @mouseleave="isPlaying && (showControls = false)"
  >
    <video
      ref="videoRef"
      :src="videoUrl"
      :autoplay="autoplay"
      preload="metadata"
      playsinline
      @timeupdate="handleTimeUpdate"
      @loadedmetadata="handleMetadata"
      @loadeddata="handleLoadedData"
      @loadstart="handleLoadStart"
      @ended="handleEnded"
      @play="handlePlay"
      @pause="handlePause"
      @error="handleError"
      @click="togglePlay"
    />

    <!-- Loading indicator -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner" />
    </div>

    <!-- Error overlay -->
    <div v-if="hasError" class="error-overlay">
      <div class="error-content">
        <span class="error-icon">&#9888;</span>
        <span class="error-text">{{ errorMessage }}</span>
        <button class="retry-btn" @click="videoRef?.load()">重试</button>
      </div>
    </div>

    <!-- Controls overlay -->
    <transition name="fade">
      <div v-show="showControls" class="controls">
        <!-- Play/Pause button -->
        <button class="control-btn" :title="isPlaying ? '暂停' : '播放'" @click.stop="togglePlay">
          <span v-if="isPlaying">&#9646;&#9646;</span>
          <span v-else>&#9654;</span>
        </button>

        <!-- Skip backward -->
        <button class="control-btn skip-btn" title="后退10秒" @click.stop="skipBackward(10)">
          <span class="skip-text">10</span>
          <span class="skip-icon">&#8634;</span>
        </button>

        <!-- Progress bar -->
        <div class="progress-bar" title="跳转" @click.stop="seek" @mousemove="handleSeekbarHover">
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: progress + '%' }" />
          </div>
        </div>

        <!-- Skip forward -->
        <button class="control-btn skip-btn" title="快进10秒" @click.stop="skipForward(10)">
          <span class="skip-icon">&#8635;</span>
          <span class="skip-text">10</span>
        </button>

        <!-- Time display -->
        <span class="time-display">{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</span>

        <!-- Volume control -->
        <div class="volume-control">
          <button class="control-btn" :title="isMuted ? '取消静音' : '静音'" @click.stop="toggleMute">
            <span v-if="isMuted || volume === 0">&#128263;</span>
            <span v-else-if="volume < 0.5">&#128266;</span>
            <span v-else>&#128266;</span>
          </button>
          <div class="volume-slider" @click.stop="setVolume">
            <div class="volume-track">
              <div
                class="volume-fill"
                :style="{ width: (isMuted ? 0 : volume * 100) + '%' }"
              />
            </div>
          </div>
        </div>

        <!-- Fullscreen -->
        <button class="control-btn" title="全屏" @click.stop="toggleFullscreen">
          <span v-if="isFullscreen">&#9747;</span>
          <span v-else>&#9974;</span>
        </button>
      </div>
    </transition>

    <!-- Big play button (shown when paused) -->
    <transition name="fade">
      <div v-if="!isPlaying && !loading && !hasError" class="big-play-overlay" @click="togglePlay">
        <div class="big-play-btn">&#9654;</div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.video-player {
  position: relative;
  background: #000;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  border-radius: 8px;
  overflow: hidden;
  user-select: none;
}

video {
  width: 100%;
  display: block;
  cursor: pointer;
}

/* Loading overlay */
.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid rgba(255, 255, 255, 0.3);
  border-top-color: #409eff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Error overlay */
.error-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.8);
}

.error-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: white;
}

.error-icon {
  font-size: 48px;
  color: #f56c6c;
}

.error-text {
  font-size: 16px;
}

.retry-btn {
  padding: 8px 24px;
  background: #409eff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.retry-btn:hover {
  background: #66b1ff;
}

/* Controls */
.controls {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.85));
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.control-btn {
  background: none;
  border: none;
  color: white;
  font-size: 18px;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 4px;
  transition: background 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 36px;
}

.control-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.skip-btn {
  position: relative;
  font-size: 12px;
}

.skip-icon {
  font-size: 18px;
}

.skip-text {
  font-size: 10px;
  font-weight: bold;
  position: absolute;
}

/* Progress bar */
.progress-bar {
  flex: 1;
  cursor: pointer;
  padding: 8px 0;
  margin: 0 4px;
}

.progress-track {
  height: 4px;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 2px;
  position: relative;
}

.progress-bar:hover .progress-track {
  height: 6px;
}

.progress-fill {
  height: 100%;
  background: #409eff;
  border-radius: 2px;
  position: relative;
}

.progress-fill::after {
  content: '';
  position: absolute;
  right: -6px;
  top: 50%;
  transform: translateY(-50%);
  width: 12px;
  height: 12px;
  background: #409eff;
  border-radius: 50%;
  opacity: 0;
  transition: opacity 0.2s;
}

.progress-bar:hover .progress-fill::after {
  opacity: 1;
}

/* Time display */
.time-display {
  color: white;
  font-size: 13px;
  min-width: 100px;
  text-align: center;
  font-family: monospace;
}

/* Volume control */
.volume-control {
  display: flex;
  align-items: center;
  gap: 4px;
}

.volume-slider {
  width: 80px;
  cursor: pointer;
  padding: 8px 0;
}

.volume-track {
  height: 4px;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 2px;
}

.volume-fill {
  height: 100%;
  background: white;
  border-radius: 2px;
}

/* Big play button */
.big-play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.3);
  cursor: pointer;
}

.big-play-btn {
  width: 72px;
  height: 72px;
  background: rgba(0, 0, 0, 0.7);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  color: white;
  transition: transform 0.2s, background 0.2s;
}

.big-play-overlay:hover .big-play-btn {
  transform: scale(1.1);
  background: rgba(64, 158, 255, 0.9);
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Fullscreen styles */
.video-player:fullscreen {
  max-width: none;
}

.video-player:fullscreen video {
  height: 100vh;
  object-fit: contain;
}
</style>
