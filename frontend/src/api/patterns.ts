import { post } from './client'
import type { PatternDetectionRequest, PatternDetectionResult } from '@/types/api'

export const patternsApi = {
  detect: (data: PatternDetectionRequest) =>
    post<PatternDetectionResult>('/patterns/detect', data),
}
