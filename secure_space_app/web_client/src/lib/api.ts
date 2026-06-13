export const API_BASE = '/api';

export class ApiClient {
  private token: string | null = null;
  private userId: string | null = null;

  setToken(token: string) {
    this.token = token;
  }

  setUserId(userId: string) {
    this.userId = userId;
  }

  getUserId() {
    return this.userId;
  }

  private async fetch(endpoint: string, options: RequestInit = {}) {
    const headers: Record<string, string> = {
      ...((options.headers as any) || {})
    };
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }
    if (!options.body || typeof options.body === 'string') {
        headers['Content-Type'] = 'application/json';
    }

    const res = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API Error: ${res.status} ${text}`);
    }

    // Check if response is json
    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return res.json();
    }
    return res.blob();
  }

  async register(userId: string, publicKeyPem: string) {
    const data = await this.fetch('/users/register', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, public_key: publicKeyPem })
    });
    this.setToken(data.token);
    this.setUserId(data.user_id);
    return data;
  }

  async loginChallenge(userId: string): Promise<{ ephemeral_public_key: string, encrypted_token: string }> {
    const res = await fetch('/api/users/login/challenge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId }),
    });
    if (!res.ok) {
      throw new Error(`API Error: ${res.status} ${await res.text()}`);
    }
    return res.json();
  }

  async getUsers(): Promise<{user_id: string, public_key: string}[]> {
    return this.fetch('/users');
  }

  async createSpace(spaceId: string) {
    return this.fetch('/spaces/create', {
      method: 'POST',
      body: JSON.stringify({ space_id: spaceId, creator_id: this.userId })
    });
  }

  async addMember(spaceId: string, userId: string, encryptedKeyHex: string) {
    return this.fetch('/spaces/add_member', {
      method: 'POST',
      body: JSON.stringify({ space_id: spaceId, user_id: userId, encrypted_key: encryptedKeyHex })
    });
  }

  async getSpaceKey(spaceId: string, userId: string) {
    return this.fetch(`/spaces/${spaceId}/key?user_id=${encodeURIComponent(userId)}`);
  }

  async getSpaceMembers(spaceId: string): Promise<{space_id: string, members: string[]}> {
    return this.fetch(`/spaces/${spaceId}/members`);
  }

  async sendDM(recipientId: string, encryptedPayloadHex: string, type: string = 'text') {
    return this.fetch('/messages/send', {
      method: 'POST',
      body: JSON.stringify({
        sender_id: this.userId,
        recipient_id: recipientId,
        payload_type: type,
        encrypted_payload: encryptedPayloadHex
      })
    });
  }

  async sendSpaceMessage(spaceId: string, encryptedPayloadHex: string, type: string = 'text') {
    return this.fetch('/messages/send', {
      method: 'POST',
      body: JSON.stringify({
        sender_id: this.userId,
        space_id: spaceId,
        payload_type: type,
        encrypted_payload: encryptedPayloadHex
      })
    });
  }

  async getMessages(userId?: string, spaceId?: string) {
    let url = `/messages`;
    const params = new URLSearchParams();
    if (userId) params.append('user_id', userId);
    if (spaceId) params.append('space_id', spaceId);
    if (params.toString()) url += `?${params.toString()}`;
    return this.fetch(url);
  }
}

export const api = new ApiClient();
