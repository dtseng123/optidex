import { imageDir } from "./dir"
import fs from "fs"
import path from "path"

export const genImgList: string[] = []

let latestGenImg = ''
let isVideoPlaying = false
let videoPlaybackMarker = '' 

// Visual mode types
export type VisualMode = {
  type: 'detection' | 'recording' | 'playback'
  framePath: string
  // For recording mode:
  videoPath?: string       // Where to save the video
  duration?: number        // Recording duration in seconds
  recordingScript?: string // Path to recording script
  // For detection mode:
  detectionScript?: string // Path to detection script
  targetObjects?: string[] // Objects to detect
}

// Pending visual mode (set by tool, retrieved after TTS)
let pendingVisualMode: VisualMode | null = null

// 加载最新生成的图片路径到list中
const loadLatestGenImg = () => {
  const files = fs.readdirSync(imageDir)
  const images = files.filter((file) => /\.(jpg|png)$/.test(file))
    .sort((a, b) => {
      const aTime = fs.statSync(path.join(imageDir, a)).mtime.getTime()
      const bTime = fs.statSync(path.join(imageDir, b)).mtime.getTime()
      return bTime - aTime
    })
    .map((file) => path.join(imageDir, file))
  genImgList.push(...images)
}

loadLatestGenImg()

export const setLatestGenImg = (imgPath: string) => {
  genImgList.push(imgPath)
  latestGenImg = imgPath
}

export const getLatestGenImg = () => {
  const img = latestGenImg
  latestGenImg = ''
  return img
}

export const showLatestGenImg = () => {
  if (genImgList.length !== 0) {
    latestGenImg = genImgList[genImgList.length - 1] || ''
    return true
  } else {
    return false
  }
}

// Video playback state management (kept for backward compatibility)
export const setVideoPlaybackMarker = (marker: string) => {
  isVideoPlaying = true
}

export const isVideoPlaybackActive = () => {
  return isVideoPlaying
}

export const clearVideoPlayback = () => {
  isVideoPlaying = false
}

// Live detection state management
let isLiveDetectionActive = false

export const setLiveDetectionActive = (active: boolean) => {
  isLiveDetectionActive = active
}

export const isLiveDetectionRunning = () => {
  return isLiveDetectionActive
}

// Pending visual mode management
export const setPendingVisualMode = (mode: VisualMode | null) => {
  pendingVisualMode = mode
}

export const getPendingVisualMode = (): VisualMode | null => {
  const mode = pendingVisualMode
  pendingVisualMode = null
  return mode
}

// Video recording state management
let isRecordingActive = false

export const setVideoRecordingActive = (active: boolean) => {
  isRecordingActive = active
}

export const isVideoRecording = () => {
  return isRecordingActive
}

// Check if any visual mode is active (detection, video recording, video playback)
export const isVisualModeActive = () => {
  return isLiveDetectionActive || isRecordingActive || isVideoPlaying
}

// Check if any visual mode is pending (waiting to start after TTS)
export const hasVisualPending = () => {
  return pendingVisualMode !== null
}
