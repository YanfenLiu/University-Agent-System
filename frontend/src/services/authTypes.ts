export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  display_name?: string;
}

export interface UserInfo {
  id: string;
  username: string;
  display_name: string;
  role: 'admin' | 'user';
  avatar: string;
  status: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserInfo;
}

export interface UserPortrait {
  major: string;
  grade: string;
  interests: string[];
  skills: string[];
  competition_type: string;
  competition_level: string;
  preferred_levels: string[];
  development_goals: string[];
  available_time_per_week: string;
  team_preference: string;
  completeness: number;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail {
  id: string;
  user_id: string;
  title: string;
  state_snapshot: Record<string, unknown>;
  messages: Array<{ role: string; content: string; files?: string[] }>;
  created_at: string;
  updated_at: string;
}
