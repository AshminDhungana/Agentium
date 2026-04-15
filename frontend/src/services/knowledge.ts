/**
 * Phase 16.3: Knowledge / Citation Graph API service.
 */
import axios from 'axios';

const API_BASE = '/api/v1/knowledge';

export interface CitationNode {
  id: string;
  depth: number;
  citation_count: number;
  collection_key?: string;
}

export interface CitationEdge {
  source: string;
  target: string;
  collection_key: string;
  citation_count: number;
  last_cited_at: string | null;
}

export interface CitationGraphResponse {
  nodes: CitationNode[];
  edges: CitationEdge[];
  stats: {
    node_count: number;
    edge_count: number;
    traversal_depth: number;
  };
}

export interface TopCitedDoc {
  doc_id: string;
  collection_key: string;
  citation_count: number;
  last_cited_at: string | null;
  avg_relevance: number;
}

export interface CitationStatsResponse {
  top_cited: TopCitedDoc[];
  count: number;
}

export const knowledgeApi = {
  /**
   * BFS-traverse the citation graph from a root document.
   */
  getCitationGraph: async (
    rootId: string,
    depth: number = 2,
  ): Promise<CitationGraphResponse> => {
    const { data } = await axios.get<CitationGraphResponse>(
      `${API_BASE}/citation-graph`,
      { params: { root: rootId, depth } },
    );
    return data;
  },

  /**
   * Get the top N most-cited documents.
   */
  getCitationStats: async (
    limit: number = 20,
  ): Promise<CitationStatsResponse> => {
    const { data } = await axios.get<CitationStatsResponse>(
      `${API_BASE}/citation-stats`,
      { params: { limit } },
    );
    return data;
  },
};
