import React, { useState, useEffect } from 'react';
import { showToast } from '@/hooks/useToast';
import { skillsApi, Skill, SkillSearchResult } from '../services/skills';
import { 
  Search, BookOpen, Tag, BarChart3, CheckCircle, Plus, Trash2, 
  Edit3, X, Save, AlertTriangle, Code2, Layers, Cpu, ChevronDown, ChevronUp, MoreVertical, RefreshCw, Network
} from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { CitationGraph } from '@/components/knowledge/CitationGraph';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// Extended skill interface for creation
interface SkillFormData {
  skill_name: string;
  display_name: string;
  skill_type: string;
  domain: string;
  tags: string[];
  complexity: 'beginner' | 'intermediate' | 'advanced';
  description: string;
  prerequisites: string[];
  steps: string[];
  code_template?: string;
  examples: { input: string; output: string }[];
  common_pitfalls: string[];
  validation_criteria: string[];
}

const INITIAL_FORM_DATA: SkillFormData = {
  skill_name: '',
  display_name: '',
  skill_type: 'code_generation',
  domain: 'frontend',
  tags: [],
  complexity: 'intermediate',
  description: '',
  prerequisites: [''],
  steps: [''],
  code_template: '',
  examples: [{ input: '', output: '' }],
  common_pitfalls: [''],
  validation_criteria: ['']
};

const SKILL_TYPES = [
  'code_generation', 'analysis', 'integration', 'automation', 
  'research', 'design', 'testing', 'deployment', 'debugging', 
  'optimization', 'documentation'
];

const DOMAINS = [
  'frontend', 'backend', 'devops', 'data', 'ai', 
  'security', 'mobile', 'desktop', 'general', 'database', 'api'
];

const COMPLEXITIES = ['beginner', 'intermediate', 'advanced'] as const;

export const SkillsPage: React.FC = () => {
  const { user } = useAuthStore();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SkillSearchResult[]>([]);
  const [popularSkills, setPopularSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);
  const [formData, setFormData] = useState<SkillFormData>(INITIAL_FORM_DATA);
  const [submitting, setSubmitting] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'browse' | 'my-submissions' | 'citation-graph'>('browse');
  const [mySubmissions, setMySubmissions] = useState<Skill[]>([]);

  const userRole = user?.role as string | undefined;
  const isPrivileged = userRole === 'council' || userRole === 'head' || userRole === 'lead';
  const canAutoVerify = userRole === 'council' || userRole === 'head';

  useEffect(() => {
    loadPopularSkills();
    if (user) {
      loadMySubmissions();
    }
  }, [user?.id]);

  const loadPopularSkills = async () => {
    try {
      const skills = await skillsApi.getPopular(undefined, 9);
      setPopularSkills(skills);
    } catch (error) {
      console.error('Failed to load popular skills:', error);
    }
  };

 const loadMySubmissions = async () => {
  if (!user?.id) return; // Guard clause - don't call API if no user
  
  try {
    const allSkills = await skillsApi.search('', { creator_id: String(user.id) });
    setMySubmissions(allSkills.map(r => r.metadata));
  } catch (error) {
    console.error('Failed to load submissions:', error);
    setMySubmissions([]); // Reset on error
  }
};

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const searchResults = await skillsApi.search(query);
      setResults(searchResults);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  };

  const clearSearch = () => {
    setQuery('');
    setResults([]);
  };

  const handleCreateSkill = async (autoVerify = false) => {
    setSubmitting(true);
    try {
      const skillData = {
        ...formData,
        skill_name: formData.display_name.toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_'),
        tags: formData.tags.filter(t => t.trim()),
        prerequisites: formData.prerequisites.filter(p => p.trim()),
        steps: formData.steps.filter(s => s.trim()),
        common_pitfalls: formData.common_pitfalls.filter(p => p.trim()),
        validation_criteria: formData.validation_criteria.filter(c => c.trim()),
        examples: formData.examples.filter(e => e.input || e.output)
      };

      await skillsApi.create(skillData, autoVerify && canAutoVerify);

      setIsCreateModalOpen(false);
      setFormData(INITIAL_FORM_DATA);
      loadPopularSkills();
      loadMySubmissions();
      showToast.success(canAutoVerify ? 'Skill created and verified!' : 'Skill submitted for review.');
    } catch (error) {
      console.error('Failed to create skill:', error);
      showToast.error('Failed to create skill. Please check all required fields.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdateSkill = async () => {
    if (!editingSkill) return;
    setSubmitting(true);
    try {
      const updates = {
        ...formData,
        skill_name: formData.display_name.toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_'),
        tags: formData.tags.filter(t => t.trim()),
        prerequisites: formData.prerequisites.filter(p => p.trim()),
        steps: formData.steps.filter(s => s.trim()),
        common_pitfalls: formData.common_pitfalls.filter(p => p.trim()),
        validation_criteria: formData.validation_criteria.filter(c => c.trim()),
        examples: formData.examples.filter(e => e.input || e.output)
      };

      await skillsApi.update(editingSkill.skill_id, updates);

      setEditingSkill(null);
      setFormData(INITIAL_FORM_DATA);
      loadPopularSkills();
      loadMySubmissions();
      clearSearch();
      showToast.success('Skill updated successfully.');
    } catch (error) {
      console.error('Failed to update skill:', error);
      showToast.error('Failed to update skill.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteSkill = async (skillId: string) => {
    try {
      await skillsApi.deprecate(skillId, 'Deleted by user');
      setDeleteConfirm(null);
      loadPopularSkills();
      loadMySubmissions();
      clearSearch();
      showToast.success('Skill deleted.');
    } catch (error) {
      console.error('Failed to delete skill:', error);
      showToast.error('Failed to delete skill. You may not have permission.');
    }
  };

  const openEditModal = (skill: Skill) => {
    setEditingSkill(skill);
    setFormData({
      skill_name: skill.skill_name,
      display_name: skill.display_name,
      skill_type: skill.skill_type,
      domain: skill.domain,
      tags: skill.tags || [],
      complexity: skill.complexity as any,
      description: skill.description,
      prerequisites: skill.prerequisites?.length ? skill.prerequisites : [''],
      steps: skill.steps?.length ? skill.steps : [''],
      code_template: skill.code_template || '',
      examples: skill.examples?.length ? skill.examples : [{ input: '', output: '' }],
      common_pitfalls: skill.common_pitfalls?.length ? skill.common_pitfalls : [''],
      validation_criteria: skill.validation_criteria?.length ? skill.validation_criteria : ['']
    });
    setIsCreateModalOpen(true);
  };

  const addArrayField = (field: keyof SkillFormData) => {
    setFormData(prev => ({
      ...prev,
      [field]: [...(prev[field] as string[]), '']
    }));
  };

  const removeArrayField = (field: keyof SkillFormData, index: number) => {
    setFormData(prev => ({
      ...prev,
      [field]: (prev[field] as string[]).filter((_, i) => i !== index)
    }));
  };

  const updateArrayField = (field: keyof SkillFormData, index: number, value: string) => {
    setFormData(prev => ({
      ...prev,
      [field]: (prev[field] as string[]).map((item, i) => i === index ? value : item)
    }));
  };

  const addExample = () => {
    setFormData(prev => ({
      ...prev,
      examples: [...prev.examples, { input: '', output: '' }]
    }));
  };

  const removeExample = (index: number) => {
    setFormData(prev => ({
      ...prev,
      examples: prev.examples.filter((_, i) => i !== index)
    }));
  };

  const updateExample = (index: number, field: 'input' | 'output', value: string) => {
    setFormData(prev => ({
      ...prev,
      examples: prev.examples.map((ex, i) => i === index ? { ...ex, [field]: value } : ex)
    }));
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'verified': return 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/20';
      case 'pending': return 'bg-yellow-100 dark:bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/20';
      case 'rejected': return 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20';
      default: return 'bg-gray-100 dark:bg-gray-500/10 text-gray-700 dark:text-gray-400';
    }
  };

  return (
    <div>
      {/* Header Section */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
              <BookOpen className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              Knowledge Library
            </h2>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Search, create, and manage reusable skills and knowledge snippets
          </p>
        </div>
        <button
          onClick={() => {
            setEditingSkill(null);
            setFormData(INITIAL_FORM_DATA);
            setIsCreateModalOpen(true);
          }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors duration-150 shadow-sm"
        >
          <Plus className="w-4 h-4" />
          Add Skill
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-gray-100 dark:bg-[#0f1117] rounded-lg w-fit mb-6">
        <button
          onClick={() => setActiveTab('browse')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-all duration-150 ${
            activeTab === 'browse'
              ? 'bg-white dark:bg-[#161b27] text-gray-900 dark:text-white shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
          }`}
        >
          Browse
        </button>
        <button
          onClick={() => setActiveTab('my-submissions')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-all duration-150 ${
            activeTab === 'my-submissions'
              ? 'bg-white dark:bg-[#161b27] text-gray-900 dark:text-white shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
          }`}
        >
          My Submissions
        </button>
        <button
          onClick={() => setActiveTab('citation-graph')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-all duration-150 ${
            activeTab === 'citation-graph'
              ? 'bg-white dark:bg-[#161b27] text-gray-900 dark:text-white shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
          }`}
        >
          <span className="flex items-center gap-1.5">
            <Network className="w-3.5 h-3.5" />
            Citation Graph
          </span>
        </button>
      </div>

      {activeTab === 'browse' ? (
        <>
          {/* Search Section */}
          <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-4 mb-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search skills (e.g., 'React form validation')..."
                  className="w-full pl-10 pr-4 py-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent transition-all"
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                />
              </div>
              <button
                onClick={handleSearch}
                disabled={loading || !query.trim()}
                className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-sm"
              >
                {loading ? <LoadingSpinner size="sm" /> : <Search className="w-4 h-4" />}
                Search
              </button>
              {results.length > 0 && (
                <button
                  onClick={clearSearch}
                  className="px-4 py-2.5 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5 rounded-lg text-sm font-medium transition-colors duration-150"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          {/* Search Results */}
          {results.length > 0 && (
            <div className="mb-8">
              <div className="flex items-center gap-2 mb-4">
                <BarChart3 className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white uppercase tracking-wider">
                  Search Results
                </h3>
                <span className="px-2 py-0.5 bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-400 text-xs rounded-full">
                  {results.length}
                </span>
              </div>
              <div className="grid gap-4">
                {results.map((result) => (
                  <SkillCard 
                    key={result.skill_id} 
                    result={result} 
                    onEdit={openEditModal}
                    onDelete={setDeleteConfirm}
                    canModify={(user?.id && result.metadata.creator_id === String(user.id)) || isPrivileged}
                    expanded={expandedSkill === result.skill_id}
                    onToggle={() => setExpandedSkill(expandedSkill === result.skill_id ? null : result.skill_id)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Popular Skills */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <CheckCircle className="w-4 h-4 text-gray-500 dark:text-gray-400" />
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white uppercase tracking-wider">
                Most Used Skills
              </h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {popularSkills.map((skill) => (
                <PopularSkillCard key={skill.skill_id} skill={skill} />
              ))}
            </div>
            {popularSkills.length === 0 && (
              <div className="text-center py-12 bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535]">
                <div className="w-12 h-12 bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] rounded-xl flex items-center justify-center mx-auto mb-3">
                  <BookOpen className="w-5 h-5 text-gray-400 dark:text-gray-500" />
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400">No skills available</p>
              </div>
            )}
          </div>
        </>
      ) : activeTab === 'citation-graph' ? (
        /* Citation Graph Tab — Phase 16.3 */
        <CitationGraph />
      ) : (
        /* My Submissions Tab */
        <div className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white uppercase tracking-wider">
              Your Skill Submissions
            </h3>
            <button
              onClick={loadMySubmissions}
              className="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
          {mySubmissions.length === 0 ? (
            <div className="text-center py-12 bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535]">
              <div className="w-12 h-12 bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] rounded-xl flex items-center justify-center mx-auto mb-3">
                <Layers className="w-5 h-5 text-gray-400 dark:text-gray-500" />
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400">No submissions yet</p>
              <button
                onClick={() => setActiveTab('browse')}
                className="mt-3 text-sm text-blue-600 dark:text-blue-400 hover:underline"
              >
                Browse and create your first skill
              </button>
            </div>
          ) : (
            <div className="grid gap-4">
              {mySubmissions.map((skill) => (
                <div
                  key={skill.skill_id}
                  className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-4 hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div>
                        <h4 className="font-semibold text-gray-900 dark:text-white">
                          {skill.display_name}
                        </h4>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                          {skill.skill_id} • {skill.created_at ? `Created ${new Date(skill.created_at).toLocaleDateString()}` : ''}
                        </p>
                      </div>
                    </div>
                    <span className={`px-2.5 py-1 text-xs font-medium rounded-full border ${getStatusColor(skill.verification_status)}`}>
                      {skill.verification_status}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-3">
                    <button
                      onClick={() => openEditModal(skill)}
                      className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded-lg transition-colors"
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                      Edit
                    </button>
                    {(user?.id && skill.creator_id === String(user.id) || isPrivileged) && (
                      <button
                        onClick={() => setDeleteConfirm(skill.skill_id)}
                        className="flex items-center gap-1 px-3 py-1.5 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        Delete
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Create/Edit Modal */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white dark:bg-[#161b27] rounded-2xl border border-gray-200 dark:border-[#1e2535] shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-[#1e2535]">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                  {editingSkill ? <Edit3 className="w-5 h-5 text-blue-600 dark:text-blue-400" /> : <Plus className="w-5 h-5 text-blue-600 dark:text-blue-400" />}
                </div>
                <div>
                  <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                    {editingSkill ? 'Edit Skill' : 'Create New Skill'}
                  </h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {editingSkill ? 'Update skill details and content' : 'Add a new reusable skill to the library'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setIsCreateModalOpen(false);
                  setEditingSkill(null);
                  setFormData(INITIAL_FORM_DATA);
                }}
                className="p-2 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Basic Info */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Display Name *
                  </label>
                  <input
                    type="text"
                    value={formData.display_name}
                    onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                    placeholder="e.g., React Form Validation with Zod"
                    className="w-full px-4 py-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Skill Type *
                  </label>
                  <select
                    value={formData.skill_type}
                    onChange={(e) => setFormData({ ...formData, skill_type: e.target.value })}
                    className="w-full px-4 py-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                  >
                    {SKILL_TYPES.map(type => (
                      <option key={type} value={type}>{type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Domain *
                  </label>
                  <select
                    value={formData.domain}
                    onChange={(e) => setFormData({ ...formData, domain: e.target.value })}
                    className="w-full px-4 py-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                  >
                    {DOMAINS.map(domain => (
                      <option key={domain} value={domain}>{domain.charAt(0).toUpperCase() + domain.slice(1)}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Complexity *
                  </label>
                  <select
                    value={formData.complexity}
                    onChange={(e) => setFormData({ ...formData, complexity: e.target.value as any })}
                    className="w-full px-4 py-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                  >
                    {COMPLEXITIES.map(c => (
                      <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Tags (comma separated)
                  </label>
                  <input
                    type="text"
                    value={formData.tags.join(', ')}
                    onChange={(e) => setFormData({ ...formData, tags: e.target.value.split(',').map(t => t.trim()) })}
                    placeholder="react, forms, validation, typescript"
                    className="w-full px-4 py-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                  />
                </div>
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Description *
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Describe what this skill does, when to use it, and why it's valuable..."
                  rows={3}
                  className="w-full px-4 py-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all resize-none"
                />
              </div>

              {/* Steps */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Steps *
                </label>
                <div className="space-y-2">
                  {formData.steps.map((step, idx) => (
                    <div key={idx} className="flex gap-2">
                      <span className="flex-shrink-0 w-8 h-8 flex items-center justify-center bg-gray-100 dark:bg-[#1e2535] text-gray-500 dark:text-gray-400 text-xs font-medium rounded-lg">
                        {idx + 1}
                      </span>
                      <input
                        type="text"
                        value={step}
                        onChange={(e) => updateArrayField('steps', idx, e.target.value)}
                        placeholder={`Step ${idx + 1}...`}
                        className="flex-1 px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                      />
                      {formData.steps.length > 1 && (
                        <button
                          onClick={() => removeArrayField('steps', idx)}
                          className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                  <button
                    onClick={() => addArrayField('steps')}
                    className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium"
                  >
                    <Plus className="w-4 h-4" />
                    Add Step
                  </button>
                </div>
              </div>

              {/* Code Template */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Code Template
                </label>
                <div className="relative">
                  <Code2 className="absolute left-3 top-3 w-4 h-4 text-gray-400 dark:text-gray-500" />
                  <textarea
                    value={formData.code_template}
                    onChange={(e) => setFormData({ ...formData, code_template: e.target.value })}
                    placeholder="// Paste your code template here..."
                    rows={6}
                    className="w-full pl-10 pr-4 py-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm font-mono text-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all resize-none"
                  />
                </div>
              </div>

              {/* Prerequisites */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Prerequisites
                </label>
                <div className="space-y-2">
                  {formData.prerequisites.map((prereq, idx) => (
                    <div key={idx} className="flex gap-2">
                      <input
                        type="text"
                        value={prereq}
                        onChange={(e) => updateArrayField('prerequisites', idx, e.target.value)}
                        placeholder="e.g., Basic knowledge of React hooks"
                        className="flex-1 px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                      />
                      {formData.prerequisites.length > 1 && (
                        <button
                          onClick={() => removeArrayField('prerequisites', idx)}
                          className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                  <button
                    onClick={() => addArrayField('prerequisites')}
                    className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium"
                  >
                    <Plus className="w-4 h-4" />
                    Add Prerequisite
                  </button>
                </div>
              </div>

              {/* Examples */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Examples
                </label>
                <div className="space-y-3">
                  {formData.examples.map((example, idx) => (
                    <div key={idx} className="p-4 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Example {idx + 1}</span>
                        {formData.examples.length > 1 && (
                          <button
                            onClick={() => removeExample(idx)}
                            className="p-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded transition-colors"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Input</label>
                        <textarea
                          value={example.input}
                          onChange={(e) => updateExample(idx, 'input', e.target.value)}
                          placeholder="Input scenario..."
                          rows={2}
                          className="w-full px-3 py-2 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all resize-none"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Output</label>
                        <textarea
                          value={example.output}
                          onChange={(e) => updateExample(idx, 'output', e.target.value)}
                          placeholder="Expected output..."
                          rows={2}
                          className="w-full px-3 py-2 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all resize-none"
                        />
                      </div>
                    </div>
                  ))}
                  <button
                    onClick={addExample}
                    className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium"
                  >
                    <Plus className="w-4 h-4" />
                    Add Example
                  </button>
                </div>
              </div>

              {/* Common Pitfalls */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Common Pitfalls
                </label>
                <div className="space-y-2">
                  {formData.common_pitfalls.map((pitfall, idx) => (
                    <div key={idx} className="flex gap-2">
                      <AlertTriangle className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-2" />
                      <input
                        type="text"
                        value={pitfall}
                        onChange={(e) => updateArrayField('common_pitfalls', idx, e.target.value)}
                        placeholder="Common mistake to avoid..."
                        className="flex-1 px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                      />
                      {formData.common_pitfalls.length > 1 && (
                        <button
                          onClick={() => removeArrayField('common_pitfalls', idx)}
                          className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                  <button
                    onClick={() => addArrayField('common_pitfalls')}
                    className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium"
                  >
                    <Plus className="w-4 h-4" />
                    Add Pitfall
                  </button>
                </div>
              </div>

              {/* Validation Criteria */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Validation Criteria *
                </label>
                <div className="space-y-2">
                  {formData.validation_criteria.map((criteria, idx) => (
                    <div key={idx} className="flex gap-2">
                      <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0 mt-2" />
                      <input
                        type="text"
                        value={criteria}
                        onChange={(e) => updateArrayField('validation_criteria', idx, e.target.value)}
                        placeholder="How to verify this skill is correctly applied..."
                        className="flex-1 px-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
                      />
                      {formData.validation_criteria.length > 1 && (
                        <button
                          onClick={() => removeArrayField('validation_criteria', idx)}
                          className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                  <button
                    onClick={() => addArrayField('validation_criteria')}
                    className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium"
                  >
                    <Plus className="w-4 h-4" />
                    Add Criterion
                  </button>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between p-6 border-t border-gray-200 dark:border-[#1e2535] bg-gray-50 dark:bg-[#0f1117]">
              <div className="text-xs text-gray-500 dark:text-gray-400">
                * Required fields
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setIsCreateModalOpen(false);
                    setEditingSkill(null);
                    setFormData(INITIAL_FORM_DATA);
                  }}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-[#2a3347] rounded-lg text-sm font-medium transition-colors"
                >
                  Cancel
                </button>
                {editingSkill ? (
                  <button
                    onClick={handleUpdateSkill}
                    disabled={submitting || !formData.display_name || !formData.description || formData.steps.filter(s => s.trim()).length === 0}
                    className="flex items-center gap-2 px-6 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                  >
                    {submitting ? <LoadingSpinner size="sm" /> : <Save className="w-4 h-4" />}
                    Update Skill
                  </button>
                ) : (
                  <div className="flex gap-2">
                    {!canAutoVerify && (
                      <button
                        onClick={() => handleCreateSkill(false)}
                        disabled={submitting || !formData.display_name || !formData.description || formData.steps.filter(s => s.trim()).length === 0}
                        className="flex items-center gap-2 px-4 py-2 bg-gray-200 dark:bg-[#2a3347] text-gray-800 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-[#3a4357] rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {submitting ? <LoadingSpinner size="sm" /> : 'Submit for Review'}
                      </button>
                    )}
                    <button
                      onClick={() => handleCreateSkill(canAutoVerify)}
                      disabled={submitting || !formData.display_name || !formData.description || formData.steps.filter(s => s.trim()).length === 0}
                      className="flex items-center gap-2 px-6 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                    >
                      {submitting ? <LoadingSpinner size="sm" /> : <Save className="w-4 h-4" />}
                      {canAutoVerify ? 'Create & Verify' : 'Create Skill'}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white dark:bg-[#161b27] rounded-2xl border border-gray-200 dark:border-[#1e2535] shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-xl bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
                <AlertTriangle className="w-6 h-6 text-red-600 dark:text-red-400" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-gray-900 dark:text-white">Delete Skill?</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">This action cannot be undone.</p>
              </div>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-300 mb-6">
              Are you sure you want to delete this skill? It will be marked as deprecated and removed from search results.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg text-sm font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteSkill(deleteConfirm)}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 dark:hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                <Trash2 className="w-4 h-4" />
                Delete Skill
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Updated SkillCard with expand/collapse and actions
const SkillCard: React.FC<{ 
  result: SkillSearchResult; 
  onEdit: (skill: Skill) => void;
  onDelete: (id: string) => void;
  canModify: boolean;
  expanded: boolean;
  onToggle: () => void;
}> = ({ result, onEdit, onDelete, canModify, expanded, onToggle }) => (
  <div className={`bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150 overflow-hidden ${expanded ? 'ring-2 ring-blue-500 dark:ring-blue-400' : ''}`}>
    <div className="p-5">
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center gap-3">
          <h3 className="font-semibold text-gray-900 dark:text-white text-base cursor-pointer hover:text-blue-600 dark:hover:text-blue-400 transition-colors" onClick={onToggle}>
            {result.metadata.display_name}
          </h3>
          <span className={`px-2 py-0.5 text-xs font-medium rounded-full border ${result.metadata.verification_status === 'verified' ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/20' : result.metadata.verification_status === 'pending' ? 'bg-yellow-100 dark:bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/20' : 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20'}`}>
            {result.metadata.verification_status}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-2 py-1 bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 text-xs font-semibold rounded-full border border-blue-200 dark:border-blue-500/20">
            {(result.relevance_score * 100).toFixed(0)}% match
          </span>
          <button onClick={onToggle} className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
            {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
          </button>
        </div>
      </div>
      
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 line-clamp-2">
        {result.metadata.description}
      </p>

      <div className="flex gap-2 mb-4 flex-wrap">
        <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-blue-50 dark:bg-blue-500/5 text-blue-700 dark:text-blue-400 text-xs font-medium rounded-lg border border-blue-100 dark:border-blue-500/10">
          <Tag className="w-3 h-3" />
          {result.metadata.domain}
        </span>
        <span className="px-2.5 py-1 bg-green-50 dark:bg-green-500/5 text-green-700 dark:text-green-400 text-xs font-medium rounded-lg border border-green-100 dark:border-green-500/10">
          {result.metadata.skill_type}
        </span>
        <span className="px-2.5 py-1 bg-purple-50 dark:bg-purple-500/5 text-purple-700 dark:text-purple-400 text-xs font-medium rounded-lg border border-purple-100 dark:border-purple-500/10">
          {result.metadata.complexity}
        </span>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
          <span className="flex items-center gap-1">
            <CheckCircle className="w-3.5 h-3.5 text-green-500 dark:text-green-400" />
            {(result.metadata.success_rate * 100).toFixed(0)}% success
          </span>
          <span>•</span>
          <span>{result.metadata.usage_count} uses</span>
        </div>
        
        {canModify && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => onEdit(result.metadata)}
              className="p-2 text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded-lg transition-colors"
              title="Edit skill"
            >
              <Edit3 className="w-4 h-4" />
            </button>
            <button
              onClick={() => onDelete(result.skill_id)}
              className="p-2 text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors"
              title="Delete skill"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>

    {/* Expanded Content */}
    {expanded && (
      <div className="border-t border-gray-200 dark:border-[#1e2535] p-5 bg-gray-50 dark:bg-[#0f1117]">
        <div className="relative">
          <pre className="text-xs bg-white dark:bg-[#161b27] text-gray-700 dark:text-gray-300 p-4 rounded-lg border border-gray-200 dark:border-[#2a3347] overflow-x-auto font-mono">
            <code>{result.content_preview}</code>
          </pre>
        </div>
        <div className="mt-4 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
          <span>ID: {result.skill_id}</span>
          <span>•</span>
          <span>Collection: {(result as any).collection ?? 'N/A'}</span>
        </div>
      </div>
    )}
  </div>
);

const PopularSkillCard: React.FC<{ skill: Skill }> = ({ skill }) => (
  <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-4 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150 cursor-pointer group">
    <div className="flex items-start justify-between mb-2">
      <h4 className="font-semibold text-gray-900 dark:text-white text-sm group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
        {skill.display_name}
      </h4>
      <div className="w-6 h-6 rounded-md bg-gray-100 dark:bg-[#1e2535] flex items-center justify-center group-hover:bg-blue-100 dark:group-hover:bg-blue-500/10 transition-colors">
        <BookOpen className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 group-hover:text-blue-600 dark:group-hover:text-blue-400" />
      </div>
    </div>
    
    <p className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2 mb-3">
      {skill.description}
    </p>

    <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
      <span className="flex items-center gap-1">
        <CheckCircle className="w-3 h-3 text-green-500 dark:text-green-400" />
        {(skill.success_rate * 100).toFixed(0)}%
      </span>
      <span>{skill.usage_count} uses</span>
    </div>
  </div>
);