import { useEffect, useState, useRef } from 'react'
import { fetchRecommendations, refreshRecommendations, fetchRecommendationPatch } from '../api'
import type { Recommendation, PatchResult } from '../types'

interface Props {
  onSelectPatch: (patch: PatchResult) => void
}

export default function ExercisePanel({ onSelectPatch }: Props) {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [patchLoadingId, setPatchLoadingId] = useState<string | null>(null)
  const hasLoaded = useRef(false)

  const loadRecs = () => {
    setLoading(true)
    fetchRecommendations()
      .then(setRecommendations)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!hasLoaded.current) {
      loadRecs()
      hasLoaded.current = true
    }
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await refreshRecommendations()
      loadRecs()
    } catch (err) {
      console.error(err)
    } finally {
      setRefreshing(false)
    }
  }

  const handleSelect = async (rec: Recommendation) => {
    setPatchLoadingId(rec.id)
    try {
      const patch = await fetchRecommendationPatch(rec.id)
      onSelectPatch(patch)
    } catch (err) {
      console.error(err)
    } finally {
      setPatchLoadingId(null)
    }
  }

  if (loading && recommendations.length === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
        <div className="spinner" style={{ marginRight: 10 }} /> Loading exercises…
      </div>
    )
  }

  // Group by level
  const grouped = recommendations.reduce((acc, r) => {
    if (!acc[r.level]) acc[r.level] = []
    acc[r.level].push(r)
    return acc
  }, {} as Record<string, Recommendation[]>)

  const levels = ['Easy', 'Medium', 'Hard']

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 20, background: 'var(--bg-base)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>Architecture & Improvement Exercises</h2>
        <button 
          onClick={handleRefresh} 
          disabled={refreshing}
          style={{
            padding: '6px 12px',
            background: 'var(--bg-panel)',
            border: '1px solid var(--border)',
            borderRadius: 4,
            color: 'var(--text)',
            fontSize: 12,
            cursor: refreshing ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6
          }}
        >
          {refreshing ? <div className="spinner" style={{ width: 10, height: 10, borderWidth: 1.5 }} /> : '↻'}
          Refresh
        </button>
      </div>

      {recommendations.length === 0 && !loading && (
        <div style={{ textAlign: 'center', marginTop: 60, color: 'var(--text-muted)' }}>
          No exercises generated yet. Click refresh to start.
        </div>
      )}

      {levels.map(level => (
        grouped[level] && (
          <div key={level} style={{ marginBottom: 32 }}>
            <h3 style={{ 
              fontSize: 12, 
              textTransform: 'uppercase', 
              letterSpacing: '0.05em', 
              color: level === 'Easy' ? 'var(--c-endpoint)' : level === 'Medium' ? 'var(--c-class)' : 'var(--c-model)',
              borderBottom: '1px solid var(--border)',
              paddingBottom: 8,
              marginBottom: 16
            }}>
              {level}
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
              {grouped[level].map(rec => (
                <div 
                  key={rec.id}
                  onClick={() => handleSelect(rec)}
                  style={{
                    background: 'var(--bg-panel)',
                    border: '1px solid var(--border)',
                    borderRadius: 8,
                    padding: 16,
                    cursor: patchLoadingId === rec.id ? 'wait' : 'pointer',
                    transition: 'transform 0.1s, border-color 0.1s',
                    position: 'relative'
                  }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
                >
                  <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8, color: 'var(--text)' }}>
                    {rec.title}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.5, marginBottom: 12 }}>
                    {rec.description}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    <span style={{ 
                      fontSize: 10, 
                      background: 'var(--bg-base)', 
                      padding: '2px 6px', 
                      borderRadius: 4, 
                      fontFamily: 'monospace',
                      color: 'var(--text-muted)'
                    }}>
                      {rec.file}
                    </span>
                  </div>
                  {patchLoadingId === rec.id && (
                    <div style={{ 
                      position: 'absolute', inset: 0, 
                      background: 'rgba(0,0,0,0.2)', 
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      borderRadius: 8
                    }}>
                       <div className="spinner" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      ))}
    </div>
  )
}
