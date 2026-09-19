<script setup lang="ts">
import { computed, ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { recordPlay, updateProgress } from '@/api/videos'
import { listSubtitles, subtitleTrackUrl } from '@/api/subtitles'
import { playerPrefs } from '@/composables/playerPrefs'
import { isTypingTarget } from '@/composables/typingGuard'
import type { Subtitle } from '@/types/subtitle'

interface Props {
  videoId: number
  videoUrl: string
  autoplay?: boolean
  /** Seconds the last session stopped at, skipped when it is not worth resuming. */
  startAt?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  autoplay: false,
  startAt: null,
})

const emit = defineEmits<{
  (e: 'play'): void
  (e: 'pause'): void
  (e: 'ended'): void
  (e: 'error', error: Event): void
  (e: 'resumed', atSeconds: number): void
}>()

const videoRef = ref<HTMLVideoElement>()
const playerRef = ref<HTMLDivElement>()
const progressBarRef = ref<HTMLDivElement>()
const isPlaying = ref(false)
const showControls = ref(true)
const currentTime = ref(0)
const duration = ref(0)
const progress = ref(0)
const isSeeking = ref(false)
const seekPercent = ref(0)
const loopStart = ref<number | null>(null)
const loopEnd = ref<number | null>(null)
const volume = ref(playerPrefs.volume)
const isMuted = ref(playerPrefs.muted)
const isFullscreen = ref(false)
const loading = ref(true)
const hasError = ref(false)
const errorMessage = ref('')
const subtitles = ref<Subtitle[]>([])
const activeSubtitleId = ref<number | null>(null)
const showSubtitleMenu = ref(false)
const playbackRate = ref(playerPrefs.rate)
const showRateMenu = ref(false)

const rateOptions = [0.5, 0.75, 1, 1.25, 1.5, 2]

let controlsTimeout: ReturnType<typeof setTimeout> | null = null
let progressInterval: ReturnType<typeof setInterval> | null = null
let hasRecordedPlay = false
let resumedThisLoad = false
/** Cue times before any offset was applied, so moving the delay never drifts. */
const cueBases = new Map<number, Array<[number, number]>>()

/** Push the remembered choices onto the element. */
function applyPrefs() {
  const video = videoRef.value
  if (!video) return
  video.volume = playerPrefs.volume
  video.muted = playerPrefs.muted
  video.playbackRate = playerPrefs.rate
  applySubtitleSize()
}

/**
 * Cues inherit the video element's font size, so overriding it here scales the
 * subtitle box without fighting the player's own ``::cue`` rules.
 */
function applySubtitleSize() {
  const video = videoRef.value
  if (!video) return
  video.style.fontSize = playerPrefs.subtitleSize ? `${playerPrefs.subtitleSize}px` : ''
}

/**
 * Cue times are mutable, which is the only way to offset a subtitle without
 * re-rendering it ourselves. The originals are kept so the offset is absolute.
 */
function captureCueBases(subtitleId: number, track: TextTrack) {
  // A track that is still loading reports an empty cue list, so an empty list
  // must not count as "already captured" — the load handler tries again.
  if (!track.cues?.length || cueBases.has(subtitleId)) return
  cueBases.set(
    subtitleId,
    Array.from({ length: track.cues.length }, (_, i) => {
      const cue = track.cues![i]
      return [cue.startTime, cue.endTime]
    }),
  )
}

function refreshCueTiming() {
  const tracks = videoRef.value?.textTracks
  if (!tracks) return
  subtitles.value.forEach((subtitle, index) => {
    const track = tracks[index]
    const bases = cueBases.get(subtitle.id)
    if (!track?.cues || !bases) return
    for (let i = 0; i < track.cues.length; i++) {
      const base = bases[i]
      if (!base) continue
      track.cues[i].startTime = Math.max(0, base[0] + playerPrefs.subtitleDelay)
      track.cues[i].endTime = Math.max(0, base[1] + playerPrefs.subtitleDelay)
    }
  })
}

function bindTrackTiming() {
  const video = videoRef.value
  if (!video) return
  const tracks = video.textTracks
  const elements = Array.from(video.querySelectorAll('track')) as HTMLTrackElement[]
  subtitles.value.forEach((subtitle, index) => {
    const track = tracks[index]
    if (!track) return
    if (track.cues?.length) {
      captureCueBases(subtitle.id, track)
      refreshCueTiming()
      return
    }
    // 浏览器要到字幕被启用时才拉取轨道，而 load 只在 <track> 元素上发，
    // TextTrack 上的那个事件 Chromium 从来不发。
    elements[index]?.addEventListener(
      'load',
      () => {
        captureCueBases(subtitle.id, track)
        refreshCueTiming()
      },
      { once: true },
    )
  })
}

function setSubtitleDelay(seconds: number) {
  playerPrefs.subtitleDelay = Math.min(15, Math.max(-15, Math.round(seconds * 10) / 10))
  refreshCueTiming()
}

function setSubtitleSize(pixels: number) {
  playerPrefs.subtitleSize = pixels === 0 ? 0 : Math.min(40, Math.max(14, pixels))
  applySubtitleSize()
}

function selectRate(rate: number) {
  playbackRate.value = rate
  showRateMenu.value = false
  if (videoRef.value) videoRef.value.playbackRate = rate
}

watch([volume, isMuted], ([nextVolume, nextMuted]) => {
  playerPrefs.volume = nextVolume
  playerPrefs.muted = nextMuted
})

watch(playbackRate, (rate) => {
  playerPrefs.rate = rate
})

watch(() => playerPrefs.subtitleDelay, refreshCueTiming)

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
  applyLoopBoundary()
}

function handleMetadata() {
  if (!videoRef.value) return
  duration.value = videoRef.value.duration
  loading.value = false
  applyPrefs()
  resumeFromStart()
}

/**
 * Jump to the stored position once the file is measurable.
 *
 * The head and the tail are skipped: resuming 3 seconds in looks like a glitch,
 * and resuming a finished title would land nowhere.
 */
function resumeFromStart() {
  const video = videoRef.value
  const at = props.startAt
  if (resumedThisLoad || !video || at == null || !isFinite(duration.value) || duration.value <= 0) {
    return
  }
  if (at <= 3 || at >= duration.value - 5) return
  resumedThisLoad = true
  video.currentTime = at
  currentTime.value = at
  progress.value = (at / duration.value) * 100
  emit('resumed', Math.floor(at))
}

/**
 * Store the playhead so history and 继续观看 follow it.
 *
 * The interval below is the safety net; the moments where the user actually
 * stops moving (pause, end, released seek bar) are where the position is worth
 * recording right away.
 */
function reportProgress(atSeconds?: number) {
  if (!props.videoId || !hasRecordedPlay) return
  const at = atSeconds ?? videoRef.value?.currentTime ?? currentTime.value
  updateProgress(props.videoId, Math.floor(at)).catch(console.error)
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
  reportProgress()
  emit('pause')
}

function handleEnded() {
  isPlaying.value = false
  // The browser leaves the playhead at the very end, so report the duration:
  // that is what turns the history row into 已完成 and drops it from 继续观看.
  reportProgress(duration.value)
  emit('ended')
}

function handleLoadStart() {
  loading.value = true
  hasError.value = false
  errorMessage.value = ''
  resumedThisLoad = false
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

function seekToPosition(clientX: number) {
  const video = videoRef.value
  const bar = progressBarRef.value
  if (!video || !bar || !isFinite(duration.value) || duration.value <= 0) return

  const rect = bar.getBoundingClientRect()
  if (rect.width <= 0) return

  const percent = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
  seekPercent.value = percent * 100
  video.currentTime = percent * duration.value
}

function startSeek(e: PointerEvent) {
  isSeeking.value = true
  seekToPosition(e.clientX)
  // 监听 window 而不是进度条，指针拖出进度条或从别处松开都能继续跟手
  window.addEventListener('pointermove', moveSeek)
  window.addEventListener('pointerup', endSeek)
  window.addEventListener('pointercancel', endSeek)
}

function moveSeek(e: PointerEvent) {
  if (!isSeeking.value) return
  seekToPosition(e.clientX)
}

function endSeek() {
  const wasSeeking = isSeeking.value
  isSeeking.value = false
  window.removeEventListener('pointermove', moveSeek)
  window.removeEventListener('pointerup', endSeek)
  window.removeEventListener('pointercancel', endSeek)
  if (wasSeeking) reportProgress()
}

// 拖拽中直接跟随指针，避免等待浏览器完成 seek 时进度条回跳
const fillPercent = computed(() => (isSeeking.value ? seekPercent.value : progress.value))

// ---------- A-B 段重放 ----------

const isLoopMarked = computed(() => loopStart.value !== null || loopEnd.value !== null)

const isLoopActive = computed(
  () =>
    loopStart.value !== null &&
    loopEnd.value !== null &&
    loopEnd.value > loopStart.value,
)

// 终点必须落在起点之后，否则按钮保持禁用，避免出现无意义的区间
const canMarkEnd = computed(
  () => loopStart.value !== null && currentTime.value > loopStart.value,
)

/** A-B 区间在进度条上的高亮段 */
const loopBand = computed(() => {
  const start = loopStart.value
  const end = loopEnd.value
  if (start === null || end === null || end <= start || !duration.value) return null
  return {
    left: (start / duration.value) * 100,
    width: ((end - start) / duration.value) * 100,
  }
})

function markLoopStart() {
  const at = videoRef.value?.currentTime ?? 0
  loopStart.value = at
  if (loopEnd.value !== null && loopEnd.value <= at) loopEnd.value = null
}

function markLoopEnd() {
  if (!canMarkEnd.value) return
  loopEnd.value = videoRef.value?.currentTime ?? 0
}

function clearLoop() {
  loopStart.value = null
  loopEnd.value = null
}

function applyLoopBoundary() {
  const video = videoRef.value
  const start = loopStart.value
  const end = loopEnd.value
  if (!video || start === null || end === null || end <= start) return
  if (video.currentTime >= end) video.currentTime = start
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

async function loadSubtitles() {
  activeSubtitleId.value = null
  showSubtitleMenu.value = false
  cueBases.clear()
  subtitles.value = []
  if (!props.videoId) return

  try {
    subtitles.value = await listSubtitles(props.videoId)
    await nextTick()
    bindTrackTiming()
  } catch (err) {
    console.error('Failed to load subtitles:', err)
  }
}

function applyTrackMode() {
  const tracks = videoRef.value?.textTracks
  if (!tracks) return
  subtitles.value.forEach((subtitle, index) => {
    const track = tracks[index]
    if (track) {
      track.mode = subtitle.id === activeSubtitleId.value ? 'showing' : 'hidden'
    }
  })
}

async function selectSubtitle(subtitleId: number | null) {
  activeSubtitleId.value = subtitleId
  showSubtitleMenu.value = false
  await nextTick()
  applyTrackMode()
}

function toggleSubtitleMenu() {
  showSubtitleMenu.value = !showSubtitleMenu.value
}

function subtitleLabel(subtitle: Subtitle): string {
  return subtitle.label || subtitle.language || `字幕 ${subtitle.id}`
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
  progressInterval = setInterval(() => {
    if (isPlaying.value) {
      reportProgress()
    }
  }, 30000) // Report every 30 seconds
}

// Keyboard shortcuts
function handleKeydown(e: KeyboardEvent) {
  if (!videoRef.value) return
  // The detail page has a title and description box; typing a space there must
  // not pause the video behind it.
  if (isTypingTarget(e.target)) return

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
  applyPrefs()
  loadSubtitles()
  startProgressReporting()
  document.addEventListener('fullscreenchange', handleFullscreenChange)
  document.addEventListener('keydown', handleKeydown)
  showControlsTemporarily()
})

onUnmounted(() => {
  endSeek()
  if (progressInterval) {
    clearInterval(progressInterval)
  }
  if (controlsTimeout) {
    clearTimeout(controlsTimeout)
  }
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
  document.removeEventListener('keydown', handleKeydown)

  // Report final progress
  reportProgress()
})

watch(() => props.videoId, () => {
  hasRecordedPlay = false
  resumedThisLoad = false
  showRateMenu.value = false
  isSeeking.value = false
  seekPercent.value = 0
  clearLoop()
  currentTime.value = 0
  duration.value = 0
  progress.value = 0
  loading.value = true
  hasError.value = false
  loadSubtitles()
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
    >
      <track
        v-for="subtitle in subtitles"
        :key="subtitle.id"
        kind="subtitles"
        :src="subtitleTrackUrl(videoId, subtitle.id)"
        :srclang="subtitle.language || 'und'"
        :label="subtitleLabel(subtitle)"
      />
    </video>

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
        <div
          ref="progressBarRef"
          class="progress-bar"
          title="跳转"
          @pointerdown.stop="startSeek"
        >
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: fillPercent + '%' }" />
            <div
              v-if="loopBand"
              class="progress-loop"
              :style="{ left: loopBand.left + '%', width: loopBand.width + '%' }"
            />
          </div>
        </div>

        <!-- Skip forward -->
        <button class="control-btn skip-btn" title="快进10秒" @click.stop="skipForward(10)">
          <span class="skip-icon">&#8635;</span>
          <span class="skip-text">10</span>
        </button>

        <!-- A-B 段重放 -->
        <div class="loop-control" :class="{ 'is-looping': isLoopActive }">
          <button
            class="control-btn loop-btn"
            :class="{ 'is-active': loopStart !== null }"
            :title="loopStart === null ? '设置 A 点（当前播放位置）' : `A 点：${formatTime(loopStart)}`"
            @click.stop="markLoopStart"
          >
            A
          </button>
          <button
            class="control-btn loop-btn"
            :class="{ 'is-active': loopEnd !== null }"
            :disabled="!canMarkEnd"
            :title="loopEnd === null ? '设置 B 点（需晚于 A 点）' : `B 点：${formatTime(loopEnd)}`"
            @click.stop="markLoopEnd"
          >
            B
          </button>
          <button
            v-if="isLoopMarked"
            class="control-btn loop-clear"
            title="清除 A-B 区间"
            @click.stop="clearLoop"
          >
            &#10005;
          </button>
        </div>

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

        <!-- Playback speed -->
        <div class="rate-control">
          <button
            class="control-btn rate-btn"
            :class="{ 'is-active': playbackRate !== 1 }"
            title="倍速"
            @click.stop="showRateMenu = !showRateMenu"
          >
            {{ playbackRate }}x
          </button>
          <div v-if="showRateMenu" class="rate-menu">
            <button
              v-for="rate in rateOptions"
              :key="rate"
              class="subtitle-menu-item"
              :class="{ 'is-active': playbackRate === rate }"
              @click.stop="selectRate(rate)"
            >
              {{ rate }}x
            </button>
          </div>
        </div>

        <!-- Subtitles -->
        <div v-if="subtitles.length" class="subtitle-control">
          <button
            class="control-btn subtitle-btn"
            :class="{ 'is-active': activeSubtitleId !== null }"
            title="字幕"
            @click.stop="toggleSubtitleMenu"
          >
            CC
          </button>
          <div v-if="showSubtitleMenu" class="subtitle-menu">
            <button
              class="subtitle-menu-item"
              :class="{ 'is-active': activeSubtitleId === null }"
              @click.stop="selectSubtitle(null)"
            >
              关闭
            </button>
            <button
              v-for="subtitle in subtitles"
              :key="subtitle.id"
              class="subtitle-menu-item"
              :class="{ 'is-active': activeSubtitleId === subtitle.id }"
              @click.stop="selectSubtitle(subtitle.id)"
            >
              {{ subtitleLabel(subtitle) }}
            </button>

            <div class="cue-settings">
              <div class="cue-setting">
                <span class="cue-setting-label">字号</span>
                <div class="cue-stepper">
                  <button class="cue-step" title="调小" @click.stop="setSubtitleSize(playerPrefs.subtitleSize - 2)">
                    &#8722;
                  </button>
                  <span class="cue-value">{{ playerPrefs.subtitleSize || '自动' }}</span>
                  <button class="cue-step" title="调大" @click.stop="setSubtitleSize(playerPrefs.subtitleSize + 2)">
                    &#43;
                  </button>
                </div>
                <button
                  v-if="playerPrefs.subtitleSize"
                  class="cue-reset"
                  @click.stop="setSubtitleSize(0)"
                >
                  自动
                </button>
              </div>
              <div class="cue-setting">
                <span class="cue-setting-label">延迟</span>
                <div class="cue-stepper">
                  <button class="cue-step" title="提前 0.5 秒" @click.stop="setSubtitleDelay(playerPrefs.subtitleDelay - 0.5)">
                    &#8722;
                  </button>
                  <span class="cue-value">{{ playerPrefs.subtitleDelay.toFixed(1) }}s</span>
                  <button class="cue-step" title="延后 0.5 秒" @click.stop="setSubtitleDelay(playerPrefs.subtitleDelay + 0.5)">
                    &#43;
                  </button>
                </div>
                <button
                  v-if="playerPrefs.subtitleDelay"
                  class="cue-reset"
                  @click.stop="setSubtitleDelay(0)"
                >
                  归零
                </button>
              </div>
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

video::cue {
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  font-family: inherit;
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
  border-top-color: #7c6cff;
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
  background: #7c6cff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.retry-btn:hover {
  background: #9d8fff;
}

/* Controls */
.controls {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  /* 暂停时大播放按钮覆盖整个画面，控制条必须浮在其上，否则进度条点不到 */
  z-index: 2;
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
  touch-action: none;
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
  background: #7c6cff;
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
  background: #7c6cff;
  border-radius: 50%;
  opacity: 0;
  transition: opacity 0.2s;
}

.progress-bar:hover .progress-fill::after {
  opacity: 1;
}

/* A-B 区间在进度条上是一扇半透明小窗 */
.progress-loop {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.25);
  border-left: 2px solid #b8adff;
  border-right: 2px solid #b8adff;
  box-shadow: 0 0 8px rgba(124, 108, 255, 0.55);
}

/* A-B 段重放：默认与控制条上其他按钮一样保持透明 */
.loop-control {
  display: flex;
  align-items: center;
  gap: 2px;
  border-radius: 999px;
  transition:
    box-shadow 0.2s,
    background 0.2s;
}

.loop-control.is-looping {
  background: rgba(124, 108, 255, 0.14);
  box-shadow: inset 0 0 0 1px rgba(157, 143, 255, 0.4);
}

.loop-btn {
  min-width: 28px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.loop-btn.is-active {
  color: #b8adff;
}

.loop-btn:disabled {
  color: rgba(255, 255, 255, 0.28);
  cursor: default;
}

.loop-btn:disabled:hover {
  background: none;
}

.loop-clear {
  min-width: 26px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
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

/* Subtitle control */
.subtitle-control {
  position: relative;
}

.subtitle-btn {
  font-size: 12px;
  font-weight: bold;
  letter-spacing: 0.5px;
}

.subtitle-btn.is-active {
  color: #7c6cff;
}

.subtitle-menu {
  position: absolute;
  bottom: 44px;
  right: 0;
  min-width: 120px;
  background: rgba(0, 0, 0, 0.9);
  border-radius: 6px;
  padding: 4px 0;
  display: flex;
  flex-direction: column;
}

.subtitle-menu-item {
  background: none;
  border: none;
  color: white;
  font-size: 13px;
  text-align: left;
  padding: 8px 14px;
  cursor: pointer;
  white-space: nowrap;
}

.subtitle-menu-item:hover {
  background: rgba(255, 255, 255, 0.15);
}

.subtitle-menu-item.is-active {
  color: #7c6cff;
}

/* 倍速：与控制条其他按钮一致，未打开菜单时保持透明 */
.rate-control {
  position: relative;
}

.rate-btn {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.3px;
}

.rate-btn.is-active {
  color: #b8adff;
}

.rate-menu {
  position: absolute;
  bottom: 44px;
  left: 50%;
  transform: translateX(-50%);
  min-width: 72px;
  background: rgba(0, 0, 0, 0.9);
  border-radius: 6px;
  padding: 4px 0;
  display: flex;
  flex-direction: column;
}

/* 字幕菜单底部的字号与延迟 */
.cue-settings {
  margin-top: 4px;
  padding: 8px 14px 6px;
  border-top: 1px solid rgba(255, 255, 255, 0.14);
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 190px;
}

.cue-setting {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.82);
}

.cue-setting-label {
  width: 28px;
  flex-shrink: 0;
}

.cue-stepper {
  display: flex;
  align-items: center;
  gap: 2px;
}

.cue-step {
  background: none;
  border: 1px solid rgba(255, 255, 255, 0.28);
  color: white;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  cursor: pointer;
  line-height: 1;
  font-size: 13px;
}

.cue-step:hover {
  background: rgba(255, 255, 255, 0.16);
}

.cue-value {
  min-width: 42px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.cue-reset {
  background: none;
  border: none;
  color: rgba(255, 255, 255, 0.6);
  font-size: 11px;
  cursor: pointer;
  padding: 0;
}

.cue-reset:hover {
  color: #b8adff;
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
