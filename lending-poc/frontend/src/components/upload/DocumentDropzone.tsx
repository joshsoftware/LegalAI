import { useCallback, useId, useRef, useState, type DragEvent } from 'react'
import { cn } from '@/lib/utils'
import { ACCEPTED_FILE_EXTENSIONS, MAX_FILE_SIZE_MB } from '@/lib/documentTypes'

interface DocumentDropzoneProps {
  label: string
  onFileSelected: (file: File) => void
  error?: string
}

/**
 * Drag-and-drop + browse target for a single document slot.
 */
export function DocumentDropzone({ label, onFileSelected, error }: DocumentDropzoneProps) {
  const [isDragActive, setIsDragActive] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const inputId = useId()

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault()
      setIsDragActive(false)
      const file = event.dataTransfer.files[0]
      if (file) onFileSelected(file)
    },
    [onFileSelected]
  )

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label={`Upload ${label}`}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            inputRef.current?.click()
          }
        }}
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragActive(true)
        }}
        onDragLeave={() => setIsDragActive(false)}
        onDrop={handleDrop}
        className={cn(
          'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-8 text-center transition-all duration-150',
          isDragActive
            ? 'border-brand-500 bg-brand-50 shadow-inner'
            : 'border-slate-300 bg-slate-50/50 hover:border-brand-300 hover:bg-brand-50/40',
          error && 'border-red-400 bg-red-50/40'
        )}
      >
        <div
          className={cn(
            'mb-2 flex h-9 w-9 items-center justify-center rounded-full text-base transition-colors',
            isDragActive ? 'bg-brand-100 text-brand-600' : 'bg-slate-100 text-slate-400'
          )}
          aria-hidden="true"
        >
          ↑
        </div>
        <p className="text-sm font-medium text-slate-700">Drag &amp; drop {label} here</p>
        <p className="mt-1 text-xs text-slate-500">
          or <span className="font-medium text-brand-600">browse</span> to upload
        </p>
        <p className="mt-2 text-xs text-slate-400">
          Accepted: {ACCEPTED_FILE_EXTENSIONS.join(', ')} — up to {MAX_FILE_SIZE_MB}MB
        </p>
      </div>
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        className="sr-only"
        accept={ACCEPTED_FILE_EXTENSIONS.join(',')}
        aria-label={`Browse for ${label} file`}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onFileSelected(file)
          e.target.value = ''
        }}
      />
      {error && <p className="mt-1.5 text-xs font-medium text-red-600">{error}</p>}
    </div>
  )
}
