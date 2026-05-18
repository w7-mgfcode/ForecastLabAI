/** Column descriptor for CSV export: a row key plus a human-readable header. */
export interface CsvColumn<T> {
  key: keyof T & string
  header: string
}

/** Quote a single CSV field per RFC 4180 (wrap + double internal quotes). */
function quoteField(value: unknown): string {
  let str = value === null || value === undefined ? '' : String(value)
  // CSV formula injection: a spreadsheet executes a cell whose value begins
  // with =, +, -, @, or a control char (tab / CR). Prefix a single quote so
  // the value is rendered as literal text instead of an evaluated formula.
  if (/^[=+\-@\t\r]/.test(str)) {
    str = `'${str}`
  }
  if (/[",\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

/**
 * Serialize rows to an RFC 4180 CSV string.
 *
 * Always emits the header row; rows are joined with CRLF. Empty `rows`
 * yields a header-only string.
 */
export function toCsv<T>(rows: T[], columns: CsvColumn<T>[]): string {
  const header = columns.map((column) => quoteField(column.header)).join(',')
  const body = rows.map((row) =>
    columns.map((column) => quoteField(row[column.key])).join(',')
  )
  return [header, ...body].join('\r\n')
}

/** Trigger a browser download of `csv` content as `filename`. */
export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
