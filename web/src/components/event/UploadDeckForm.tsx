export interface UploadDeckFormProps {
  deckListText: string
  onDeckListChange: (v: string) => void
  onSubmit: () => void
  onCancel: () => void
  uploading: boolean
}

export default function UploadDeckForm({
  deckListText,
  onDeckListChange,
  onSubmit,
  onCancel,
  uploading,
}: UploadDeckFormProps) {
  return (
    <>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.75rem' }}>
        Paste a deck list in Moxfield style (section headers: Commander, Mainboard, Sideboard; lines like &quot;4 Lightning Bolt&quot;).
      </p>
      <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', marginBottom: '1rem' }}>
        <span className="label">Deck list</span>
        <textarea
          value={deckListText}
          onChange={(e) => onDeckListChange(e.target.value)}
          placeholder={`Mainboard\n4 Lightning Bolt\n2 Counterspell\n\nSideboard\n2 Flusterstorm`}
          rows={14}
          style={{ width: '100%', boxSizing: 'border-box', fontFamily: 'inherit', fontSize: '0.9rem', resize: 'vertical' }}
          aria-label="Deck list"
        />
      </label>
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <button type="button" className="btn btn-primary" onClick={onSubmit} disabled={uploading}>
          {uploading ? 'Uploading…' : 'Upload'}
        </button>
        <button type="button" className="btn" onClick={onCancel} disabled={uploading}>
          Cancel
        </button>
      </div>
    </>
  )
}
