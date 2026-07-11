export interface CardOption {
  id: string;
  label: string;
  value: string;
}

export type CardInputType = 'single_select' | 'multi_select';

export interface CardQuestion {
  id: string;
  question: string;
  input_type: CardInputType;
  required: boolean;
  options: CardOption[];
}

export interface StructuredInputCardPayload {
  card_id: string;
  card_group_id?: string | null;
  title?: string | null;
  questions: CardQuestion[];
  expires_at?: string | null; // ISO-8601 or null
}

export interface CardAnswerQuestion {
  question_id: string;
  selected_option_ids: string[]; // excludes "Other"
  other_text: string | null;
}

export interface StructuredInputAnswer {
  card_id: string;
  card_group_id?: string | null;
  answers: CardAnswerQuestion[];
}
