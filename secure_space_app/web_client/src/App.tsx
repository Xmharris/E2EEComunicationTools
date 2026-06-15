import { useState, useEffect } from 'react';
import { 
  Typography, Box, TextField, Button, Paper, 
  List, ListItemButton, ListItemText, Divider, CssBaseline, ThemeProvider, createTheme,
  AppBar, Toolbar, Tabs, Tab, Dialog, DialogTitle, DialogContent, DialogActions, Select, MenuItem, Card, CardContent
} from '@mui/material';
import LockIcon from '@mui/icons-material/Lock';
import EventIcon from '@mui/icons-material/Event';
import GroupIcon from '@mui/icons-material/Group';
import ChatIcon from '@mui/icons-material/Chat';
import { api } from './lib/api';
import { 
  generateKeyPair, deriveSharedKey, encryptAESGCM, decryptAESGCM, 
  exportPrivateKey, importPrivateKey, generateSpaceKey, encryptSpaceKeyForUser, decryptSpaceKeyFromUser 
} from './lib/crypto';

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#90caf9' },
    secondary: { main: '#f48fb1' },
    background: { default: '#0a1929', paper: '#132f4c' }
  },
  typography: { fontFamily: 'Inter, Roboto, sans-serif' }
});

export default function App() {
  const [userId, setUserId] = useState('');
  const [isRegistered, setIsRegistered] = useState(false);
  const [keys, setKeys] = useState<{privateKey: CryptoKey, publicKeyPem: string} | null>(null);
  
  const [users, setUsers] = useState<any[]>([]);
  const [spaces, setSpaces] = useState<any[]>([]);
  const [spaceKeys, setSpaceKeys] = useState<Record<string, CryptoKey>>({});
  
  const [viewMode, setViewMode] = useState<'dms' | 'spaces' | 'meetings'>('dms');
  const [selectedUser, setSelectedUser] = useState<any | null>(null);
  const [selectedSpaceId, setSelectedSpaceId] = useState<string | null>(null);
  
  const [messages, setMessages] = useState<any[]>([]);
  const [inputText, setInputText] = useState('');
  const [tabIndex, setTabIndex] = useState(0);
  const [importKeyFile, setImportKeyFile] = useState<File | null>(null);

  const [createSpaceOpen, setCreateSpaceOpen] = useState(false);
  const [newSpaceName, setNewSpaceName] = useState('');
  
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteUserId, setInviteUserId] = useState('');
  
  const [meetingOpen, setMeetingOpen] = useState(false);
  const [meetingMeta, setMeetingMeta] = useState({ title: '', time: '', location: '', description: '' });
  
  const [allMeetings, setAllMeetings] = useState<any[]>([]);
  const [searchLocation, setSearchLocation] = useState('');
  const [searchType, setSearchType] = useState('All');
  const [externalMeetings, setExternalMeetings] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  useEffect(() => {
    const session = localStorage.getItem('groundedmind_session');
    if (session) {
      try {
        const { userId, token, privateKeyPem, publicKeyPem } = JSON.parse(session);
        api.setToken(token);
        api.setUserId(userId);
        setUserId(userId);
        importPrivateKey(privateKeyPem).then(privKey => {
          setKeys({ privateKey: privKey, publicKeyPem });
          setIsRegistered(true);
        });
      } catch (e) {
        console.error("Failed to restore session", e);
      }
    }
  }, []);

  const fetchInitialData = async () => {
    try {
      const uList = await api.getUsers();
      const sList = await api.getSpaces();
      setUsers(uList.filter((u: any) => u.user_id !== userId));
      setSpaces(sList);
      
      const newKeys: Record<string, CryptoKey> = {};
      for (const s of sList) {
        try {
          const keyInfo = await api.getSpaceKey(s.space_id, userId);
          let creatorPubKey = keys!.publicKeyPem;
          if (keyInfo.creator_id !== userId) {
            const creator = uList.find((u: any) => u.user_id === keyInfo.creator_id);
            if (creator) creatorPubKey = creator.public_key;
          }
          newKeys[s.space_id] = await decryptSpaceKeyFromUser(keyInfo.encrypted_key, creatorPubKey, keys!.privateKey);
        } catch (e) {
          console.error('Failed to load space key for', s.space_id, e);
        }
      }
      setSpaceKeys(newKeys);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (isRegistered && keys && userId) {
      fetchInitialData();
    }
  }, [isRegistered, keys, userId]);

  const handleRegister = async () => {
    if (!userId) return;
    try {
      const newKeys = await generateKeyPair();
      const data = await api.register(userId, newKeys.publicKeyPem);
      const privateKeyPem = await exportPrivateKey(newKeys.privateKey);
      
      localStorage.setItem('groundedmind_session', JSON.stringify({
        userId, token: data.token, privateKeyPem, publicKeyPem: newKeys.publicKeyPem
      }));

      setKeys(newKeys);
      setIsRegistered(true);
    } catch (e) {
      console.error(e);
      alert('Registration failed: Username may already exist');
    }
  };

  const handleLogin = async () => {
    if (!userId || !importKeyFile) return;
    try {
      const pemText = await importKeyFile.text();
      const privateKey = await importPrivateKey(pemText);
      const challengeData = await api.loginChallenge(userId);
      const sharedKey = await deriveSharedKey(privateKey, challengeData.ephemeral_public_key);
      const decToken = await decryptAESGCM(sharedKey, challengeData.encrypted_token);
      const tokenStr = new TextDecoder().decode(decToken);
      
      api.setToken(tokenStr);
      api.setUserId(userId);
      
      localStorage.setItem('groundedmind_session', JSON.stringify({
        userId, token: tokenStr, privateKeyPem: pemText, publicKeyPem: ""
      }));

      // We need public key for creator logic in group chats, so we should fetch it or generate it
      // actually we can just fetch it from /api/users
      const allU = await api.getUsers();
      const me = allU.find((u: any) => u.user_id === userId);
      
      setKeys({ privateKey, publicKeyPem: me?.public_key || "" });
      setIsRegistered(true);
    } catch (e) {
      console.error(e);
      alert('Login failed: Invalid key or user');
    }
  };

  const fetchMessages = async () => {
    if (!keys || !userId) return;
    try {
      if (viewMode === 'dms' && selectedUser) {
        const msgs = await api.getMessages(userId);
        const filteredMsgs = msgs.filter((m: any) => 
          (m.sender_id === userId && m.recipient_id === selectedUser.user_id) ||
          (m.sender_id === selectedUser.user_id && m.recipient_id === userId)
        );
        const sharedKey = await deriveSharedKey(keys.privateKey, selectedUser.public_key);
        const decryptedMsgs = await Promise.all(filteredMsgs.map(async (m: any) => {
          try {
            const dec = await decryptAESGCM(sharedKey, m.encrypted_payload);
            const text = new TextDecoder().decode(dec);
            return { ...m, plaintext: m.payload_type === 'meeting' ? `[Meeting: ${JSON.parse(text).title}]` : text, raw: text };
          } catch {
            return { ...m, plaintext: '[Decryption Failed]' };
          }
        }));
        setMessages(decryptedMsgs);
      } else if (viewMode === 'spaces' && selectedSpaceId && spaceKeys[selectedSpaceId]) {
        const msgs = await api.getMessages(undefined, selectedSpaceId);
        const spaceKey = spaceKeys[selectedSpaceId];
        const decryptedMsgs = await Promise.all(msgs.map(async (m: any) => {
          try {
            const dec = await decryptAESGCM(spaceKey, m.encrypted_payload);
            const text = new TextDecoder().decode(dec);
            return { ...m, plaintext: m.payload_type === 'meeting' ? `[Meeting: ${JSON.parse(text).title}]` : text, raw: text };
          } catch {
            return { ...m, plaintext: '[Decryption Failed]' };
          }
        }));
        setMessages(decryptedMsgs);
      } else if (viewMode === 'meetings') {
        let allMsgs: any[] = [];
        const dmMsgs = await api.getMessages(userId);
        for (const m of dmMsgs) {
          if (m.payload_type !== 'meeting') continue;
          const otherUserId = m.sender_id === userId ? m.recipient_id : m.sender_id;
          const otherUser = users.find(u => u.user_id === otherUserId);
          if (!otherUser) continue;
          try {
            const sharedKey = await deriveSharedKey(keys.privateKey, otherUser.public_key);
            const dec = await decryptAESGCM(sharedKey, m.encrypted_payload);
            const meta = JSON.parse(new TextDecoder().decode(dec));
            allMsgs.push({ ...m, meta, source: `DM with ${otherUserId}` });
          } catch (e) {}
        }
        
        for (const s of spaces) {
          if (!spaceKeys[s.space_id]) continue;
          const sMsgs = await api.getMessages(undefined, s.space_id);
          for (const m of sMsgs) {
            if (m.payload_type !== 'meeting') continue;
            try {
              const dec = await decryptAESGCM(spaceKeys[s.space_id], m.encrypted_payload);
              const meta = JSON.parse(new TextDecoder().decode(dec));
              allMsgs.push({ ...m, meta, source: `Group: ${s.space_id}` });
            } catch (e) {}
          }
        }
        
        allMsgs.sort((a, b) => new Date(a.meta.time).getTime() - new Date(b.meta.time).getTime());
        setAllMeetings(allMsgs);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (isRegistered) {
      fetchMessages();
      const interval = setInterval(fetchMessages, 3000);
      return () => clearInterval(interval);
    }
  }, [isRegistered, selectedUser, selectedSpaceId, viewMode, spaceKeys]);

  const handleSend = async () => {
    if (!inputText || !keys) return;
    try {
      if (viewMode === 'dms' && selectedUser) {
        const sharedKey = await deriveSharedKey(keys.privateKey, selectedUser.public_key);
        const encryptedHex = await encryptAESGCM(sharedKey, new TextEncoder().encode(inputText));
        await api.sendDM(selectedUser.user_id, encryptedHex, 'text');
      } else if (viewMode === 'spaces' && selectedSpaceId && spaceKeys[selectedSpaceId]) {
        const spaceKey = spaceKeys[selectedSpaceId];
        const encryptedHex = await encryptAESGCM(spaceKey, new TextEncoder().encode(inputText));
        await api.sendSpaceMessage(selectedSpaceId, encryptedHex, 'text');
      }
      setInputText('');
      fetchMessages();
    } catch (e) {
      console.error(e);
      alert('Failed to send message');
    }
  };

  const handleSearchExternal = async () => {
    if (!searchLocation) return;
    setIsSearching(true);
    try {
      const results = await api.getExternalMeetings(searchLocation, searchType);
      setExternalMeetings(results);
    } catch (e) {
      console.error(e);
      alert('Failed to search public meetings');
    } finally {
      setIsSearching(false);
    }
  };

  const handleCreateSpace = async () => {
    if (!newSpaceName || !keys) return;
    try {
      await api.createSpace(newSpaceName);
      const spaceKey = await generateSpaceKey();
      const encryptedKeyHex = await encryptSpaceKeyForUser(spaceKey, keys.publicKeyPem, keys.privateKey);
      await api.addMember(newSpaceName, userId, encryptedKeyHex);
      setCreateSpaceOpen(false);
      setNewSpaceName('');
      fetchInitialData();
    } catch (e) {
      console.error(e);
      alert('Failed to create support group');
    }
  };

  const handleInviteUser = async () => {
    if (!inviteUserId || !selectedSpaceId || !keys) return;
    try {
      const u = users.find(x => x.user_id === inviteUserId);
      if (!u) throw new Error("User not found");
      const spaceKey = spaceKeys[selectedSpaceId];
      if (!spaceKey) throw new Error("Space key missing");
      const encryptedKeyHex = await encryptSpaceKeyForUser(spaceKey, u.public_key, keys.privateKey);
      await api.addMember(selectedSpaceId, inviteUserId, encryptedKeyHex);
      setInviteOpen(false);
      setInviteUserId('');
      alert("Invited successfully");
    } catch (e) {
      console.error(e);
      alert('Failed to invite user');
    }
  };

  const handleScheduleMeeting = async () => {
    if (!keys || !meetingMeta.title || !meetingMeta.time) return;
    try {
      const payload = JSON.stringify(meetingMeta);
      if (viewMode === 'dms' && selectedUser) {
        const sharedKey = await deriveSharedKey(keys.privateKey, selectedUser.public_key);
        const encryptedHex = await encryptAESGCM(sharedKey, new TextEncoder().encode(payload));
        await api.sendDM(selectedUser.user_id, encryptedHex, 'meeting');
      } else if (viewMode === 'spaces' && selectedSpaceId && spaceKeys[selectedSpaceId]) {
        const spaceKey = spaceKeys[selectedSpaceId];
        const encryptedHex = await encryptAESGCM(spaceKey, new TextEncoder().encode(payload));
        await api.sendSpaceMessage(selectedSpaceId, encryptedHex, 'meeting');
      }
      setMeetingOpen(false);
      setMeetingMeta({ title: '', time: '', location: '', description: '' });
      fetchMessages();
    } catch (e) {
      console.error(e);
      alert('Failed to schedule meeting');
    }
  };

  if (!isRegistered) {
    return (
      <ThemeProvider theme={darkTheme}>
        <CssBaseline />
        <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2 }}>
          <Paper elevation={3} sx={{ p: 4, width: '100%', maxWidth: 400 }}>
            <Tabs value={tabIndex} onChange={(_, val) => setTabIndex(val)} variant="fullWidth" sx={{ mb: 3 }}>
              <Tab label="Create Identity" />
              <Tab label="Import Identity" />
            </Tabs>
            <Typography variant="h4" gutterBottom align="center" color="primary" sx={{ fontWeight: 'bold' }}>
              GroundedMind
            </Typography>
            <TextField fullWidth label="Username" variant="outlined" value={userId} onChange={(e) => setUserId(e.target.value)} sx={{ mb: 3 }} />
            {tabIndex === 0 && (
              <Button fullWidth variant="contained" size="large" onClick={handleRegister}>Generate Keys & Enter</Button>
            )}
            {tabIndex === 1 && (
              <>
                <Button variant="outlined" component="label" fullWidth sx={{ mb: 2 }}>
                  Upload Private Key (.pem)
                  <input type="file" hidden accept=".pem" onChange={(e) => { if (e.target.files?.length) setImportKeyFile(e.target.files[0]); }} />
                </Button>
                {importKeyFile && <Typography variant="caption" sx={{ display: 'block', mb: 2, textAlign: 'center' }}>Selected: {importKeyFile.name}</Typography>}
                <Button fullWidth variant="contained" size="large" onClick={handleLogin} disabled={!importKeyFile}>Log In</Button>
              </>
            )}
          </Paper>
        </Box>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <Box sx={{ display: 'flex', height: '100vh' }}>
        <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
          <Toolbar>
            <LockIcon sx={{ mr: 2 }} />
            <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>GroundedMind - {userId}</Typography>
            <Button color="inherit" onClick={async () => {
              if (!keys) return;
              const pem = await exportPrivateKey(keys.privateKey);
              const blob = new Blob([pem], { type: 'text/plain' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a'); a.href = url; a.download = `private_key.pem`; a.click(); URL.revokeObjectURL(url);
            }}>Export Key</Button>
            <Button color="inherit" onClick={() => { localStorage.removeItem('groundedmind_session'); window.location.reload(); }}>Log Out</Button>
          </Toolbar>
        </AppBar>
        
        <Box sx={{ width: 280, borderRight: '1px solid #1e4976', display: 'flex', flexDirection: 'column', mt: 8 }}>
          <Tabs value={viewMode === 'meetings' ? 2 : viewMode === 'spaces' ? 1 : 0} onChange={(_, val) => setViewMode(val === 0 ? 'dms' : val === 1 ? 'spaces' : 'meetings')} variant="fullWidth">
            <Tab icon={<ChatIcon />} aria-label="DMs" />
            <Tab icon={<GroupIcon />} aria-label="Groups" />
            <Tab icon={<EventIcon />} aria-label="Meetings" />
          </Tabs>
          <Box sx={{ overflowY: 'auto', flexGrow: 1 }}>
            <List>
              {viewMode === 'dms' && users.map((u: any) => (
                <ListItemButton key={u.user_id} selected={selectedUser?.user_id === u.user_id} onClick={() => setSelectedUser(u)}>
                  <ListItemText primary={u.user_id} />
                </ListItemButton>
              ))}
              {viewMode === 'spaces' && spaces.map((s: any) => (
                <ListItemButton key={s.space_id} selected={selectedSpaceId === s.space_id} onClick={() => setSelectedSpaceId(s.space_id)}>
                  <ListItemText primary={s.space_id} />
                </ListItemButton>
              ))}
            </List>
          </Box>
          {viewMode === 'spaces' && (
            <Box sx={{ p: 2 }}><Button fullWidth variant="outlined" onClick={() => setCreateSpaceOpen(true)}>Create Group</Button></Box>
          )}
        </Box>

        <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', mt: 8, bgcolor: 'background.default' }}>
          {viewMode === 'meetings' ? (
            <Box sx={{ p: 4, overflowY: 'auto' }}>
              <Typography variant="h4" gutterBottom>Meeting Finder</Typography>
              
              <Paper sx={{ p: 3, mb: 4, bgcolor: 'background.paper' }}>
                <Typography variant="h6" gutterBottom>Find Local Public Support Groups</Typography>
                <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                  Search for real-world NA, AA, or SMART Recovery meetings in your area.
                </Typography>
                <Box sx={{ display: 'flex', gap: 2 }}>
                  <TextField size="small" label="Zip Code or City" value={searchLocation} onChange={e => setSearchLocation(e.target.value)} sx={{ flexGrow: 1 }} />
                  <Select size="small" value={searchType} onChange={e => setSearchType(e.target.value as string)} sx={{ minWidth: 150 }}>
                    <MenuItem value="All">All Types</MenuItem>
                    <MenuItem value="AA">AA (Alcoholics Anonymous)</MenuItem>
                    <MenuItem value="NA">NA (Narcotics Anonymous)</MenuItem>
                    <MenuItem value="SMART Recovery">SMART Recovery</MenuItem>
                  </Select>
                  <Button variant="contained" onClick={handleSearchExternal} disabled={!searchLocation || isSearching}>{isSearching ? 'Searching...' : 'Search'}</Button>
                </Box>
                {externalMeetings.length > 0 && (
                  <Box sx={{ mt: 3, display: 'flex', flexWrap: 'wrap', gap: 2 }}>
                    {externalMeetings.map((m: any) => (
                      <Card key={m.id} sx={{ minWidth: 275, bgcolor: 'primary.dark' }}>
                        <CardContent>
                          <Typography sx={{ fontSize: 14 }} color="text.secondary" gutterBottom>Public Meeting • {m.type}</Typography>
                          <Typography variant="h6" component="div">{m.title}</Typography>
                          <Typography sx={{ mb: 1.5 }} color="text.secondary">{m.time}</Typography>
                          <Typography variant="body2"><strong>Location:</strong> {m.location}<br /><br />{m.description}</Typography>
                        </CardContent>
                      </Card>
                    ))}
                  </Box>
                )}
              </Paper>

              <Typography variant="h6" gutterBottom>My Encrypted Group Meetings</Typography>
              <Divider sx={{ mb: 3 }} />
              {allMeetings.length === 0 ? (
                <Typography color="textSecondary">No upcoming internal meetings scheduled.</Typography>
              ) : (
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
                  {allMeetings.map((m: any, idx) => (
                    <Card key={idx} sx={{ minWidth: 275, bgcolor: 'background.paper', mb: 2 }}>
                      <CardContent>
                        <Typography sx={{ fontSize: 14 }} color="text.secondary" gutterBottom>{m.source}</Typography>
                        <Typography variant="h6" component="div">{m.meta.title}</Typography>
                        <Typography sx={{ mb: 1.5 }} color="text.secondary">{new Date(m.meta.time).toLocaleString()}</Typography>
                        <Typography variant="body2"><strong>Location:</strong> {m.meta.location}<br />{m.meta.description}</Typography>
                      </CardContent>
                    </Card>
                  ))}
                </Box>
              )}
            </Box>
          ) : ((viewMode === 'dms' && selectedUser) || (viewMode === 'spaces' && selectedSpaceId)) ? (
            <>
              <Box sx={{ p: 2, borderBottom: '1px solid #1e4976', bgcolor: 'background.paper', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="h6">
                  {viewMode === 'dms' ? `Encrypted Chat with ${selectedUser.user_id}` : `Support Group: ${selectedSpaceId}`}
                </Typography>
                <Box>
                  <Button variant="outlined" size="small" sx={{ mr: 1 }} onClick={() => setMeetingOpen(true)}>Schedule Meeting</Button>
                  {viewMode === 'spaces' && <Button variant="outlined" size="small" onClick={() => setInviteOpen(true)}>Invite User</Button>}
                </Box>
              </Box>
              <Box sx={{ flexGrow: 1, p: 3, overflowY: 'auto' }}>
                {messages.map((m, idx) => (
                  <Box key={idx} sx={{ mb: 2, textAlign: m.sender_id === userId ? 'right' : 'left' }}>
                    <Typography variant="caption" sx={{ display: 'block', mb: 0.5, opacity: 0.7 }}>
                      {m.sender_id}
                    </Typography>
                    <Paper elevation={1} sx={{ display: 'inline-block', p: 1.5, borderRadius: 2, bgcolor: m.sender_id === userId ? 'primary.dark' : 'background.paper' }}>
                      <Typography variant="body1">{m.plaintext}</Typography>
                      <Typography variant="caption" sx={{ opacity: 0.6 }}>{new Date().toLocaleTimeString()}</Typography>
                    </Paper>
                  </Box>
                ))}
              </Box>
              <Box sx={{ p: 2, bgcolor: 'background.paper', display: 'flex' }}>
                <TextField fullWidth variant="outlined" size="small" placeholder="Type an encrypted message..." value={inputText} onChange={e => setInputText(e.target.value)} onKeyPress={e => e.key === 'Enter' && handleSend()} />
                <Button variant="contained" sx={{ ml: 2 }} onClick={handleSend}>Send</Button>
              </Box>
            </>
          ) : (
            <Box sx={{ flexGrow: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Typography color="textSecondary">Select a conversation to start messaging</Typography>
            </Box>
          )}
        </Box>
      </Box>

      {/* Dialogs */}
      <Dialog open={createSpaceOpen} onClose={() => setCreateSpaceOpen(false)}>
        <DialogTitle>Create Support Group</DialogTitle>
        <DialogContent>
          <TextField autoFocus margin="dense" label="Group Name (Space ID)" fullWidth variant="outlined" value={newSpaceName} onChange={(e) => setNewSpaceName(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateSpaceOpen(false)}>Cancel</Button>
          <Button onClick={handleCreateSpace} variant="contained">Create</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={inviteOpen} onClose={() => setInviteOpen(false)}>
        <DialogTitle>Invite User to Group</DialogTitle>
        <DialogContent>
          <Select fullWidth value={inviteUserId} onChange={(e) => setInviteUserId(e.target.value as string)} displayEmpty>
            <MenuItem value="" disabled>Select User</MenuItem>
            {users.map((u: any) => <MenuItem key={u.user_id} value={u.user_id}>{u.user_id}</MenuItem>)}
          </Select>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setInviteOpen(false)}>Cancel</Button>
          <Button onClick={handleInviteUser} variant="contained" disabled={!inviteUserId}>Invite</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={meetingOpen} onClose={() => setMeetingOpen(false)}>
        <DialogTitle>Schedule Secure Meeting</DialogTitle>
        <DialogContent>
          <TextField margin="dense" label="Title" fullWidth value={meetingMeta.title} onChange={e => setMeetingMeta({...meetingMeta, title: e.target.value})} />
          <TextField margin="dense" label="Time" type="datetime-local" fullWidth value={meetingMeta.time} onChange={e => setMeetingMeta({...meetingMeta, time: e.target.value})} />
          <TextField margin="dense" label="Location/Link" fullWidth value={meetingMeta.location} onChange={e => setMeetingMeta({...meetingMeta, location: e.target.value})} />
          <TextField margin="dense" label="Description" fullWidth multiline rows={3} value={meetingMeta.description} onChange={e => setMeetingMeta({...meetingMeta, description: e.target.value})} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMeetingOpen(false)}>Cancel</Button>
          <Button onClick={handleScheduleMeeting} variant="contained">Schedule</Button>
        </DialogActions>
      </Dialog>

    </ThemeProvider>
  );
}
