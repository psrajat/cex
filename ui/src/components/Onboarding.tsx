import { useState, useEffect } from 'react'
import { ingestRepo, listDirectories } from '../api'

interface Props {
  onComplete: () => void
}

export default function Onboarding({ onComplete }: Props) {
  const [repoDir, setRepoDir] = useState('')
  const [force, setForce] = useState(false)

  // Picker state
  const [showPicker, setShowPicker] = useState(false)
  const [pickerPath, setPickerPath] = useState('/home')
  const [dirs, setDirs] = useState<string[]>([])
  const [loadingDirs, setLoadingDirs] = useState(false)

  const [isIngesting, setIsIngesting] = useState(false)
  const [progressLog, setProgressLog] = useState<string[]>([])
  const [statusText, setStatusText] = useState('')

  useEffect(() => {
    if (showPicker) {
      setLoadingDirs(true)
      listDirectories(pickerPath)
        .then(setDirs)
        .catch(() => setDirs([]))
        .finally(() => setLoadingDirs(false))
    }
  }, [showPicker, pickerPath])

  const goUp = () => {
    const parts = pickerPath.replace(/\/$/, '').split('/')
    parts.pop()
    setPickerPath(parts.length > 0 ? parts.join('/') || '/' : '/')
  }

  const handleStart = async () => {
    if (!repoDir.trim()) return

    setIsIngesting(true)
    setProgressLog(['Starting synchronous ingestion. Please wait...'])
    setStatusText('INGESTING')

    try {
      const res = await ingestRepo({ 
        repo_dir: repoDir, 
        force
      })
      setProgressLog(prev => [...prev, res.message])
      setStatusText('DONE')
      setTimeout(() => {
        onComplete()
      }, 1000)
    } catch (error: any) {
      setProgressLog(prev => [...prev, `[FATAL] ${error.message}`])
      setStatusText('ERROR')
    } finally {
      setIsIngesting(false)
    }
  }

  return (
    <div style={{
      flex: 1, backgroundColor: 'var(--bg-base)', 
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: 40
    }}>
      <div style={{
        width: 600, background: 'var(--bg-panel)',
        border: '1px solid var(--border)', borderRadius: 8,
        padding: 32, display: 'flex', flexDirection: 'column', gap: 24
      }}>
        <div>
          <h1 style={{ margin: '0 0 8px 0', fontSize: 24, fontWeight: 700 }}>Initialize Repository</h1>
          <p style={{ margin: 0, color: 'var(--text-dim)', fontSize: 13 }}>
            Select a Python codebase to ingest and explain.
          </p>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>ABSOLUTE DIRECTORY PATH</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <input 
              type="text" 
              value={repoDir}
              onChange={e => setRepoDir(e.target.value)}
              disabled={isIngesting}
              placeholder="/home/user/my_django_project"
              style={{
                flex: 1, padding: '10px 12px',
                background: 'var(--bg-base)', border: '1px solid var(--border)',
                borderRadius: 4, color: 'var(--text)', fontSize: 13,
                fontFamily: 'monospace'
              }}
            />
            <button
               onClick={() => setShowPicker(!showPicker)}
               style={{ 
                 background: 'var(--bg-panel)', border: '1px solid var(--border)', 
                 padding: '0 16px', borderRadius: 4, color: 'var(--text)', cursor: 'pointer' 
               }}
            >Browse</button>
          </div>

          {showPicker && (
            <div style={{ 
               marginTop: 8, height: 200, border: '1px solid var(--border)', 
               borderRadius: 4, background: 'var(--bg-base)', display: 'flex', flexDirection: 'column'
            }}>
               <div style={{ padding: '8px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 8, alignItems: 'center' }}>
                  <button onClick={goUp} style={{ padding: '2px 8px' }}>..</button>
                  <span style={{ fontSize: 12, fontFamily: 'monospace' }}>{pickerPath}</span>
               </div>
               <div style={{ flex: 1, overflowY: 'auto' }}>
                  {loadingDirs ? <div style={{ padding: 12, fontSize: 12 }}>Loading...</div> : dirs.map(d => (
                    <div 
                      key={d}
                      onClick={() => setRepoDir(pickerPath === '/' ? `/${d}` : `${pickerPath}/${d}`)}
                      onDoubleClick={() => setPickerPath(pickerPath === '/' ? `/${d}` : `${pickerPath}/${d}`)}
                      style={{
                        padding: '6px 12px', cursor: 'pointer', fontSize: 13, fontFamily: 'monospace',
                        background: repoDir === (pickerPath === '/' ? `/${d}` : `${pickerPath}/${d}`) ? 'var(--bg-panel)' : 'transparent'
                      }}
                    >
                      📁 {d}
                    </div>
                  ))}
               </div>
            </div>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: isIngesting ? 'wait' : 'pointer' }}>
            <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} disabled={isIngesting} />
            Force Reload (Delete old cache and start fresh)
          </label>
        </div>

        <button 
          onClick={handleStart}
          disabled={!repoDir.trim() || isIngesting}
          style={{
            padding: '12px', background: 'var(--accent)', color: '#fff',
            border: 'none', borderRadius: 4, fontWeight: 600, fontSize: 14,
            cursor: !repoDir.trim() || isIngesting ? 'not-allowed' : 'pointer',
            opacity: !repoDir.trim() || isIngesting ? 0.6 : 1,
            marginTop: 8
          }}
        >
          {isIngesting ? 'Processing...' : 'Start Ingestion'}
        </button>

        {isIngesting && (
           <div style={{ marginTop: 16, background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 4, padding: 12, height: 80, display: 'flex', flexDirection: 'column' }}>
             <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, color: 'var(--accent)', fontWeight: 600, fontSize: 12 }}>
                <span>STATUS: {statusText}</span>
                <div className="spinner" style={{ width: 12, height: 12 }} />
             </div>
             <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column-reverse' }}>
                <div style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-dim)', whiteSpace: 'pre-wrap' }}>
                  {progressLog.join('\n')}
                </div>
             </div>
           </div>
        )}
        {!isIngesting && statusText === 'ERROR' && (
           <div style={{ marginTop: 16, background: 'var(--bg-base)', border: '1px solid #ff4444', borderRadius: 4, padding: 12, height: 80, display: 'flex', flexDirection: 'column' }}>
             <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, color: '#ff4444', fontWeight: 600, fontSize: 12 }}>
                <span>STATUS: {statusText}</span>
             </div>
             <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column-reverse' }}>
                <div style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-dim)', whiteSpace: 'pre-wrap' }}>
                  {progressLog.join('\n')}
                </div>
             </div>
           </div>
        )}
      </div>
    </div>
  )
}
