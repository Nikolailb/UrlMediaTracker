import { useMutation } from '@tanstack/react-query'
import { patternsApi } from '@/api/patterns'
import type { PatternDetectionRequest } from '@/types/api'

export function usePatternDetect() {
  return useMutation({
    mutationFn: (data: PatternDetectionRequest) => patternsApi.detect(data),
  })
}
