import { format } from 'date-fns'
import { DateRange } from 'react-day-picker'

// Helper to convert DateRange to string format for API
export function dateRangeToStrings(range: DateRange | undefined): {
  startDate: string | undefined
  endDate: string | undefined
} {
  return {
    startDate: range?.from ? format(range.from, 'yyyy-MM-dd') : undefined,
    endDate: range?.to ? format(range.to, 'yyyy-MM-dd') : undefined,
  }
}

// Helper to parse string dates to DateRange
export function stringsToDateRange(
  startDate: string | undefined,
  endDate: string | undefined
): DateRange | undefined {
  if (!startDate) return undefined
  return {
    from: new Date(startDate),
    to: endDate ? new Date(endDate) : undefined,
  }
}
