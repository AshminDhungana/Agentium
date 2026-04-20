/**
 * Phase 16.3: Interactive Citation Graph visualization.
 *
 * Uses SVG + basic force simulation (no external D3 dependency required).
 * Renders nodes (documents) and edges (citation links) with:
 *   - Node size proportional to citation_count
 *   - Node colour by collection_key
 *   - Directed edges drawn as lines with arrows
 *   - Click-to-expand (calls API with root=clicked node)
 *   - Hover tooltip showing doc ID
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { knowledgeApi, CitationNode, CitationEdge, TopCitedDoc } from '../../services/knowledge';
import {
  Search, RefreshCw, Network, BarChart3,
  ZoomIn, ZoomOut, Maximize2, Info, TrendingUp,
} from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ── Colour palette per collection ──────────────────────────────────────────
const COLLECTION_COLORS: Record<string, string> = {
  constitution: '#3b82f6',     // blue
  ethos: '#8b5cf6',            // violet
  council_memory: '#6366f1',   // indigo
  precedent: '#6366f1',
  task_patterns: '#10b981',    // emerald
  coordination_pattern: '#14b8a6', // teal
  execution_pattern: '#22c55e',// green
  best_practices: '#f59e0b',   // amber
  case_law_warning: '#ef4444', // red
  sovereign_preference: '#ec4899', // pink
  critic_case_law: '#f97316',   // orange
};

const getColor = (key: string) =>
  COLLECTION_COLORS[key] || '#64748b';

// ── Simple force simulation ────────────────────────────────────────────────
interface SimNode extends CitationNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  fx?: number;
  fy?: number;
}

function runSimulation(
  nodes: SimNode[],
  edges: CitationEdge[],
  width: number,
  height: number,
  iterations: number = 120,
) {
  const cx = width / 2;
  const cy = height / 2;

  // Init positions in a circle
  nodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / nodes.length;
    const r = Math.min(width, height) * 0.3;
    n.x = cx + r * Math.cos(angle) + (Math.random() - 0.5) * 20;
    n.y = cy + r * Math.sin(angle) + (Math.random() - 0.5) * 20;
    n.vx = 0;
    n.vy = 0;
  });

  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  const repulsion = 3000;
  const attraction = 0.005;
  const centerPull = 0.01;
  const damping = 0.85;

  for (let iter = 0; iter < iterations; iter++) {
    // Repulsion (all pairs)
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = repulsion / (dist * dist);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx -= fx; a.vy -= fy;
        b.vx += fx; b.vy += fy;
      }
    }

    // Attraction (edges)
    for (const edge of edges) {
      const src = nodeMap.get(edge.source);
      const tgt = nodeMap.get(edge.target);
      if (!src || !tgt) continue;
      const dx = tgt.x - src.x, dy = tgt.y - src.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const force = dist * attraction;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      src.vx += fx; src.vy += fy;
      tgt.vx -= fx; tgt.vy -= fy;
    }

    // Center gravity
    for (const n of nodes) {
      n.vx += (cx - n.x) * centerPull;
      n.vy += (cy - n.y) * centerPull;
    }

    // Integrate + damp
    for (const n of nodes) {
      n.vx *= damping; n.vy *= damping;
      n.x += n.vx; n.y += n.vy;
      // Keep within bounds
      n.x = Math.max(40, Math.min(width - 40, n.x));
      n.y = Math.max(40, Math.min(height - 40, n.y));
    }
  }
}

// ── Component ──────────────────────────────────────────────────────────────
export const CitationGraph: React.FC = () => {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [nodes, setNodes] = useState<SimNode[]>([]);
  const [edges, setEdges] = useState<CitationEdge[]>([]);
  const [stats, setStats] = useState<{ node_count: number; edge_count: number; traversal_depth: number } | null>(null);
  const [topCited, setTopCited] = useState<TopCitedDoc[]>([]);

  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [statsLoading, setStatsLoading] = useState(false);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const WIDTH = 800;
  const HEIGHT = 500;

  // ── Load top-cited stats on mount ──────────────────────────────────────
  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    setStatsLoading(true);
    try {
      const result = await knowledgeApi.getCitationStats(20);
      setTopCited(result.top_cited);
    } catch {
      // Stats are non-critical
    } finally {
      setStatsLoading(false);
    }
  };

  // ── Load graph from root ────────────────────────────────────────────────
  const loadGraph = useCallback(async (rootId: string, depth: number = 2) => {
    if (!rootId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await knowledgeApi.getCitationGraph(rootId.trim(), depth);
      const simNodes: SimNode[] = result.nodes.map(n => ({
        ...n,
        x: 0, y: 0, vx: 0, vy: 0,
      }));
      runSimulation(simNodes, result.edges, WIDTH, HEIGHT);
      setNodes(simNodes);
      setEdges(result.edges);
      setStats(result.stats);
      setSelectedNode(rootId.trim());
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load citation graph');
      setNodes([]);
      setEdges([]);
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSearch = () => {
    if (searchQuery.trim()) {
      loadGraph(searchQuery.trim());
    }
  };

  const handleNodeClick = (nodeId: string) => {
    setSearchQuery(nodeId);
    loadGraph(nodeId, 2);
  };

  const handleTopCitedClick = (docId: string) => {
    setSearchQuery(docId);
    loadGraph(docId, 2);
  };

  const nodeRadius = (n: SimNode) => Math.max(8, Math.min(24, 8 + (n.citation_count || 0) * 0.8));

  return (
    <div className="space-y-6">
      {/* Search bar */}
      <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-4 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Enter a document ID to explore its citation graph..."
              className="w-full pl-10 pr-4 py-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent transition-all"
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={loading || !searchQuery.trim()}
            className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-sm"
          >
            {loading ? <LoadingSpinner size="sm" /> : <Network className="w-4 h-4" />}
            Explore
          </button>
          <button
            onClick={loadStats}
            disabled={statsLoading}
            className="px-3 py-2.5 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5 rounded-lg text-sm transition-colors duration-150"
            title="Refresh stats"
          >
            <RefreshCw className={`w-4 h-4 ${statsLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-sm text-red-700 dark:text-red-400">
          <Info className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Graph + Stats row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* SVG Graph */}
        <div className="lg:col-span-2 bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] overflow-hidden shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
          {/* Graph toolbar */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-[#1e2535]">
            <div className="flex items-center gap-2">
              <Network className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              <span className="text-sm font-semibold text-gray-900 dark:text-white">
                Citation Graph
              </span>
              {stats && (
                <span className="px-2 py-0.5 bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-400 text-xs rounded-full">
                  {stats.node_count} nodes · {stats.edge_count} edges
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setZoom(z => Math.min(2, z + 0.2))}
                className="p-1.5 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
                title="Zoom in"
              >
                <ZoomIn className="w-4 h-4" />
              </button>
              <button
                onClick={() => setZoom(z => Math.max(0.3, z - 0.2))}
                className="p-1.5 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
                title="Zoom out"
              >
                <ZoomOut className="w-4 h-4" />
              </button>
              <button
                onClick={() => setZoom(1)}
                className="p-1.5 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
                title="Reset zoom"
              >
                <Maximize2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* SVG canvas */}
          <div
            ref={containerRef}
            className="relative bg-gray-50 dark:bg-[#0f1117] overflow-hidden"
            style={{ height: HEIGHT }}
          >
            {nodes.length === 0 && !loading ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400 dark:text-gray-500 gap-3">
                <Network className="w-12 h-12 opacity-40" />
                <p className="text-sm">Enter a document ID above or click a top-cited document</p>
              </div>
            ) : loading ? (
              <div className="absolute inset-0 flex items-center justify-center text-gray-400 dark:text-gray-500 gap-2">
                <LoadingSpinner size="md" />
                <span className="text-sm">Loading graph…</span>
              </div>
            ) : (
              <svg
                ref={svgRef}
                viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
                width="100%"
                height={HEIGHT}
                style={{ transform: `scale(${zoom})`, transformOrigin: 'center' }}
                className="transition-transform duration-200"
              >
                {/* Arrow marker defs */}
                <defs>
                  <marker
                    id="arrowhead"
                    markerWidth="8"
                    markerHeight="6"
                    refX="8"
                    refY="3"
                    orient="auto"
                  >
                    <polygon
                      points="0 0, 8 3, 0 6"
                      fill="#94a3b8"
                      className="dark:fill-gray-600"
                    />
                  </marker>
                </defs>

                {/* Edges */}
                {edges.map((edge, i) => {
                  const src = nodes.find(n => n.id === edge.source);
                  const tgt = nodes.find(n => n.id === edge.target);
                  if (!src || !tgt) return null;
                  const sr = nodeRadius(src);
                  const tr = nodeRadius(tgt);
                  const dx = tgt.x - src.x, dy = tgt.y - src.y;
                  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                  // Shorten line to not overlap node circles
                  const x1 = src.x + (dx / dist) * sr;
                  const y1 = src.y + (dy / dist) * sr;
                  const x2 = tgt.x - (dx / dist) * (tr + 8);
                  const y2 = tgt.y - (dy / dist) * (tr + 8);
                  const opacity = Math.min(1, 0.3 + edge.citation_count * 0.1);
                  return (
                    <line
                      key={`edge-${i}`}
                      x1={x1} y1={y1} x2={x2} y2={y2}
                      stroke="#94a3b8"
                      strokeWidth={Math.min(3, 0.5 + edge.citation_count * 0.3)}
                      strokeOpacity={opacity}
                      markerEnd="url(#arrowhead)"
                      className="dark:stroke-gray-600"
                    />
                  );
                })}

                {/* Nodes */}
                {nodes.map(node => {
                  const r = nodeRadius(node);
                  const color = getColor(node.collection_key || '');
                  const isHovered = hoveredNode === node.id;
                  const isSelected = selectedNode === node.id;
                  return (
                    <g
                      key={node.id}
                      className="cursor-pointer"
                      onMouseEnter={() => setHoveredNode(node.id)}
                      onMouseLeave={() => setHoveredNode(null)}
                      onClick={() => handleNodeClick(node.id)}
                    >
                      {/* Glow ring for selected */}
                      {isSelected && (
                        <circle
                          cx={node.x} cy={node.y} r={r + 6}
                          fill="none"
                          stroke={color}
                          strokeWidth={2}
                          strokeOpacity={0.4}
                          className="animate-pulse"
                        />
                      )}
                      {/* Node circle */}
                      <circle
                        cx={node.x} cy={node.y} r={r}
                        fill={color}
                        fillOpacity={isHovered ? 1 : 0.85}
                        stroke={isHovered ? '#fff' : color}
                        strokeWidth={isHovered ? 2.5 : 1.5}
                        strokeOpacity={isHovered ? 1 : 0.5}
                        style={{ transition: 'all 0.15s ease' }}
                      />
                      {/* Label */}
                      <text
                        x={node.x}
                        y={node.y + r + 14}
                        textAnchor="middle"
                        fontSize={10}
                        fill="#64748b"
                        className="dark:fill-gray-500 pointer-events-none select-none"
                      >
                        {node.id.length > 18 ? node.id.slice(0, 16) + '…' : node.id}
                      </text>
                      {/* Citation count badge */}
                      {node.citation_count > 0 && (
                        <>
                          <circle
                            cx={node.x + r * 0.7}
                            cy={node.y - r * 0.7}
                            r={8}
                            fill="#1e293b"
                            className="dark:fill-gray-200"
                          />
                          <text
                            x={node.x + r * 0.7}
                            y={node.y - r * 0.7 + 3.5}
                            textAnchor="middle"
                            fontSize={9}
                            fontWeight="bold"
                            fill="#fff"
                            className="dark:fill-gray-900 pointer-events-none select-none"
                          >
                            {node.citation_count}
                          </text>
                        </>
                      )}
                    </g>
                  );
                })}
              </svg>
            )}

            {/* Hover tooltip */}
            {hoveredNode && (
              <div className="absolute top-3 left-3 px-3 py-2 bg-white dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] rounded-lg shadow-lg text-xs text-gray-700 dark:text-gray-300 pointer-events-none z-10 max-w-[240px]">
                <p className="font-semibold truncate">{hoveredNode}</p>
                {(() => {
                  const n = nodes.find(nd => nd.id === hoveredNode);
                  if (!n) return null;
                  return (
                    <div className="mt-1 space-y-0.5 text-gray-500 dark:text-gray-400">
                      <p>Citations: {n.citation_count}</p>
                      {n.collection_key && <p>Collection: {n.collection_key}</p>}
                      <p>Depth: {n.depth}</p>
                    </div>
                  );
                })()}
              </div>
            )}
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-t border-gray-200 dark:border-[#1e2535]">
            <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">Collections:</span>
            {Object.entries(COLLECTION_COLORS).slice(0, 6).map(([key, color]) => (
              <div key={key} className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                <span className="text-xs text-gray-500 dark:text-gray-400">{key.replace(/_/g, ' ')}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Stats sidebar */}
        <div className="space-y-4">
          {/* Graph stats card */}
          {stats && (
            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-4 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
              <div className="flex items-center gap-2 mb-3">
                <BarChart3 className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                <span className="text-sm font-semibold text-gray-900 dark:text-white">Graph Stats</span>
              </div>
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: 'Nodes', value: stats.node_count },
                  { label: 'Edges', value: stats.edge_count },
                  { label: 'Depth', value: stats.traversal_depth },
                ].map(s => (
                  <div key={s.label} className="text-center p-2 bg-gray-50 dark:bg-[#0f1117] rounded-lg">
                    <p className="text-lg font-bold text-gray-900 dark:text-white">{s.value}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{s.label}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Top cited docs */}
          <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-200 dark:border-[#1e2535]">
              <TrendingUp className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              <span className="text-sm font-semibold text-gray-900 dark:text-white">Most Cited</span>
              <span className="ml-auto px-2 py-0.5 bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-400 text-xs rounded-full">
                {topCited.length}
              </span>
            </div>
            <div className="max-h-[360px] overflow-y-auto">
              {statsLoading ? (
                <div className="flex items-center justify-center py-8 text-gray-400 dark:text-gray-500 gap-2">
                  <LoadingSpinner size="sm" />
                  <span className="text-sm">Loading…</span>
                </div>
              ) : topCited.length === 0 ? (
                <div className="text-center py-8 text-gray-400 dark:text-gray-500">
                  <BarChart3 className="w-8 h-8 mx-auto mb-2 opacity-40" />
                  <p className="text-sm">No citation data yet</p>
                  <p className="text-xs mt-1">Citations are recorded during RAG retrieval</p>
                </div>
              ) : (
                <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                  {topCited.map((doc, i) => (
                    <button
                      key={`${doc.doc_id}-${i}`}
                      onClick={() => handleTopCitedClick(doc.doc_id)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-white/[0.03] transition-colors text-left"
                    >
                      <span className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-400">
                        {i + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-900 dark:text-white truncate">
                          {doc.doc_id}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {doc.collection_key} · relevance {(doc.avg_relevance * 100).toFixed(0)}%
                        </p>
                      </div>
                      <span className="flex-shrink-0 px-2 py-0.5 bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 text-xs font-medium rounded-full border border-blue-200 dark:border-blue-500/20">
                        {doc.citation_count}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
