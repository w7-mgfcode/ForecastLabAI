import { describe, it, expect } from 'vitest'
import { toCsv, type CsvColumn } from './csv-export'

interface Row {
  name: string
  city: string
  qty: number
}

const columns: CsvColumn<Row>[] = [
  { key: 'name', header: 'Name' },
  { key: 'city', header: 'City' },
  { key: 'qty', header: 'Quantity' },
]

describe('toCsv', () => {
  it('emits a header-only string for empty rows', () => {
    expect(toCsv([], columns)).toBe('Name,City,Quantity')
  })

  it('serializes rows joined with CRLF', () => {
    const csv = toCsv([{ name: 'Acme', city: 'Springfield', qty: 3 }], columns)
    expect(csv).toBe('Name,City,Quantity\r\nAcme,Springfield,3')
  })

  it('quotes and escapes fields containing commas and quotes', () => {
    const csv = toCsv([{ name: 'A, Inc', city: 'Say "Hi"', qty: 1 }], columns)
    expect(csv).toBe('Name,City,Quantity\r\n"A, Inc","Say ""Hi""",1')
  })

  it('quotes a field containing a newline', () => {
    const csv = toCsv([{ name: 'Line1\nLine2', city: 'X', qty: 0 }], columns)
    expect(csv).toContain('"Line1\nLine2"')
  })

  it('preserves the column order from the columns argument', () => {
    const reordered: CsvColumn<Row>[] = [
      { key: 'qty', header: 'Quantity' },
      { key: 'name', header: 'Name' },
    ]
    const csv = toCsv([{ name: 'Acme', city: 'X', qty: 7 }], reordered)
    expect(csv).toBe('Quantity,Name\r\n7,Acme')
  })

  it('renders null and undefined as empty fields', () => {
    interface NullableRow {
      a: string | null
      b: number | undefined
    }
    const nullableColumns: CsvColumn<NullableRow>[] = [
      { key: 'a', header: 'A' },
      { key: 'b', header: 'B' },
    ]
    expect(toCsv([{ a: null, b: undefined }], nullableColumns)).toBe('A,B\r\n,')
  })
})
