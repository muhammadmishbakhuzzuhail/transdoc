// © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
// Proprietary — source-available for reference only; no use, copying, or
// distribution without written permission. See LICENSE.
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
