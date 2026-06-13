import React, { useState, useEffect } from 'react';
import { 
  Container, Typography, Box, TextField, Button, Paper, 
  List, ListItem, ListItemButton, ListItemText, Divider, CssBaseline, ThemeProvider, createTheme,
  AppBar, Toolbar, Tabs, Tab
} from '@mui/material';
import LockIcon from '@mui/icons-material/Lock';
import { api } from './lib/api';
import { generateKeyPair, deriveSharedKey, encryptAESGCM, decryptAESGCM, exportPrivateKey, importPrivateKey } from './lib/crypto';

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
  const [selectedUser, setSelectedUser] = useState<any | null>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [inputText, setInputText] = useState('');
  const [tabIndex, setTabIndex] = useState(0);
  const [importKeyFile, setImportKeyFile] = useState<File | null>(null);

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
          fetchUsers();
        });
      } catch (e) {
        console.error("Failed to restore session", e);
      }
    }
  }, []);

  const handleRegister = async () => {
    if (!userId) return;
    try {
      const newKeys = await generateKeyPair();
      const data = await api.register(userId, newKeys.publicKeyPem);
      const privateKeyPem = await exportPrivateKey(newKeys.privateKey);
      
      localStorage.setItem('groundedmind_session', JSON.stringify({
        userId,
        token: data.token,
        privateKeyPem,
        publicKeyPem: newKeys.publicKeyPem
      }));

      setKeys(newKeys);
      setIsRegistered(true);
      fetchUsers();
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
      const tokenStr = await decryptAESGCM(sharedKey, challengeData.encrypted_token);
      
      api.setToken(tokenStr);
      api.setUserId(userId);
      
      localStorage.setItem('groundedmind_session', JSON.stringify({
        userId,
        token: tokenStr,
        privateKeyPem: pemText,
        publicKeyPem: ""
      }));

      setKeys({ privateKey, publicKeyPem: "" });
      setIsRegistered(true);
      fetchUsers();
    } catch (e) {
      console.error(e);
      alert('Login failed: Invalid key or user');
    }
  };

  const fetchUsers = async () => {
    try {
      const u = await api.getUsers();
      setUsers(u.filter(u => u.user_id !== userId));
    } catch (e) {
      console.error(e);
    }
  };

  const fetchMessages = async () => {
    if (!selectedUser || !keys || !userId) return;
    try {
      const msgs = await api.getMessages(userId);
      
      const filteredMsgs = msgs.filter((m: any) => 
        (m.sender_id === userId && m.recipient_id === selectedUser.user_id) ||
        (m.sender_id === selectedUser.user_id && m.recipient_id === userId)
      );
      
      const sharedKey = await deriveSharedKey(keys.privateKey, selectedUser.public_key);
      
      const decryptedMsgs = await Promise.all(filteredMsgs.map(async (m: any) => {
        try {
          const dec = await decryptAESGCM(sharedKey, m.encrypted_payload);
          return { ...m, plaintext: new TextDecoder().decode(dec) };
        } catch {
          return { ...m, plaintext: '[Decryption Failed]' };
        }
      }));

      setMessages(decryptedMsgs);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (isRegistered && selectedUser) {
      fetchMessages();
      const interval = setInterval(fetchMessages, 3000);
      return () => clearInterval(interval);
    }
  }, [isRegistered, selectedUser]);

  const handleSend = async () => {
    if (!inputText || !selectedUser || !keys) return;
    try {
      const sharedKey = await deriveSharedKey(keys.privateKey, selectedUser.public_key);
      const encryptedHex = await encryptAESGCM(sharedKey, new TextEncoder().encode(inputText));
      await api.sendDM(selectedUser.user_id, encryptedHex, 'text');
      setInputText('');
      fetchMessages();
    } catch (e) {
      console.error(e);
      alert('Failed to send message');
    }
  };

  if (!isRegistered) {
    return (
      <ThemeProvider theme={darkTheme}>
        <CssBaseline />
        <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2 }}>
          <Paper elevation={3} sx={{ p: 4, width: '100%', maxWidth: 400 }}>
            <Tabs value={tabIndex} onChange={(e, val) => setTabIndex(val)} variant="fullWidth" sx={{ mb: 3 }}>
              <Tab label="Create Identity" />
              <Tab label="Import Identity" />
            </Tabs>

            <Typography variant="h4" gutterBottom align="center" color="primary" sx={{ fontWeight: 'bold' }}>
              GroundedMind
            </Typography>
            <TextField 
              fullWidth 
              label="Username" 
              variant="outlined" 
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              sx={{ mb: 3 }}
            />

            {tabIndex === 0 && (
              <Button 
                fullWidth 
                variant="contained" 
                size="large"
                onClick={handleRegister}
              >
                Generate Keys & Enter
              </Button>
            )}

            {tabIndex === 1 && (
              <>
                <Button
                  variant="outlined"
                  component="label"
                  fullWidth
                  sx={{ mb: 2 }}
                >
                  Upload Private Key (.pem)
                  <input
                    type="file"
                    hidden
                    accept=".pem"
                    onChange={(e) => {
                      if (e.target.files && e.target.files.length > 0) {
                        setImportKeyFile(e.target.files[0]);
                      }
                    }}
                  />
                </Button>
                {importKeyFile && (
                  <Typography variant="caption" display="block" sx={{ mb: 2, textAlign: 'center' }}>
                    Selected: {importKeyFile.name}
                  </Typography>
                )}
                <Button 
                  fullWidth 
                  variant="contained" 
                  size="large"
                  onClick={handleLogin}
                  disabled={!importKeyFile}
                >
                  Log In
                </Button>
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
            <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
              GroundedMind - {userId}
            </Typography>
            <Button color="inherit" onClick={async () => {
              if (!keys) return;
              const pem = await exportPrivateKey(keys.privateKey);
              const blob = new Blob([pem], { type: 'text/plain' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `groundedmind_${userId}_private_key.pem`;
              a.click();
              URL.revokeObjectURL(url);
            }}>
              Export Key
            </Button>
            <Button color="inherit" onClick={() => {
              localStorage.removeItem('groundedmind_session');
              window.location.reload();
            }}>
              Log Out
            </Button>
          </Toolbar>
        </AppBar>
        
        <Box sx={{ width: 280, borderRight: '1px solid #1e4976', overflowY: 'auto', mt: 8 }}>
          <List>
            <ListItem><Typography variant="overline" sx={{ px: 2, color: 'primary.main' }}>Direct Messages</Typography></ListItem>
            {users.map((u) => (
              <ListItemButton 
                key={u.user_id} 
                selected={selectedUser?.user_id === u.user_id}
                onClick={() => setSelectedUser(u)}
              >
                <ListItemText primary={u.user_id} />
              </ListItemButton>
            ))}
          </List>
        </Box>

        <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', mt: 8, bgcolor: 'background.default' }}>
          {selectedUser ? (
            <>
              <Box sx={{ p: 2, borderBottom: '1px solid #1e4976', bgcolor: 'background.paper' }}>
                <Typography variant="h6">Encrypted Chat with {selectedUser.user_id}</Typography>
              </Box>
              <Box sx={{ flexGrow: 1, p: 3, overflowY: 'auto' }}>
                {messages.map((m, idx) => (
                  <Box key={idx} sx={{ mb: 2, textAlign: m.sender_id === userId ? 'right' : 'left' }}>
                    <Paper elevation={1} sx={{ 
                      display: 'inline-block', p: 1.5, borderRadius: 2, 
                      bgcolor: m.sender_id === userId ? 'primary.dark' : 'background.paper' 
                    }}>
                      <Typography variant="body1">{m.plaintext}</Typography>
                      <Typography variant="caption" sx={{ opacity: 0.6 }}>{new Date(m.timestamp).toLocaleTimeString()}</Typography>
                    </Paper>
                  </Box>
                ))}
              </Box>
              <Box sx={{ p: 2, bgcolor: 'background.paper', display: 'flex' }}>
                <TextField 
                  fullWidth variant="outlined" size="small" placeholder="Type an encrypted message..."
                  value={inputText} onChange={e => setInputText(e.target.value)}
                  onKeyPress={e => e.key === 'Enter' && handleSend()}
                />
                <Button variant="contained" sx={{ ml: 2 }} onClick={handleSend}>Send</Button>
              </Box>
            </>
          ) : (
            <Box sx={{ flexGrow: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Typography color="textSecondary">Select a user to start an encrypted conversation</Typography>
            </Box>
          )}
        </Box>
      </Box>
    </ThemeProvider>
  );
}
