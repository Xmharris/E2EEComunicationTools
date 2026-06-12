import React, { useState, useEffect } from 'react';
import { 
  Container, Typography, Box, TextField, Button, Paper, 
  List, ListItem, ListItemText, Divider, CssBaseline, ThemeProvider, createTheme,
  AppBar, Toolbar, IconButton
} from '@mui/material';
import LockIcon from '@mui/icons-material/Lock';
import { api } from './lib/api';
import { generateKeyPair, deriveSharedKey, encryptAESGCM, decryptAESGCM } from './lib/crypto';

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

  const handleRegister = async () => {
    if (!userId) return;
    try {
      const newKeys = await generateKeyPair();
      setKeys(newKeys);
      await api.register(userId, newKeys.publicKeyPem);
      setIsRegistered(true);
      fetchUsers();
    } catch (e) {
      console.error(e);
      alert('Registration failed');
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
    if (!selectedUser || !keys) return;
    try {
      const msgs = await api.getMessages(); // Get all messages
      // Filter for DM with selectedUser
      const chatMsgs = msgs.filter((m: any) => 
        (m.sender_id === userId && m.recipient_id === selectedUser.user_id) ||
        (m.sender_id === selectedUser.user_id && m.recipient_id === userId)
      );

      const sharedKey = await deriveSharedKey(keys.privateKey, selectedUser.public_key);
      
      const decryptedMsgs = await Promise.all(chatMsgs.map(async (m: any) => {
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
        <Container maxWidth="xs" sx={{ mt: 10 }}>
          <Paper elevation={6} sx={{ p: 4, display: 'flex', flexDirection: 'column', alignItems: 'center', borderRadius: 3 }}>
            <LockIcon color="primary" sx={{ fontSize: 60, mb: 2 }} />
            <Typography variant="h4" gutterBottom fontWeight="bold">GroundedMind</Typography>
            <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>End-to-End Encrypted Space</Typography>
            <TextField fullWidth label="Choose Username" variant="outlined" margin="normal" value={userId} onChange={e => setUserId(e.target.value)} />
            <Button fullWidth variant="contained" size="large" sx={{ mt: 2, borderRadius: 2 }} onClick={handleRegister}>
              Generate Keys & Enter
            </Button>
          </Paper>
        </Container>
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
          </Toolbar>
        </AppBar>
        
        <Box sx={{ width: 280, borderRight: '1px solid #1e4976', overflowY: 'auto', mt: 8 }}>
          <List>
            <ListItem><Typography variant="overline" sx={{ px: 2, color: 'primary.main' }}>Direct Messages</Typography></ListItem>
            {users.map((u) => (
              <ListItem 
                button 
                key={u.user_id} 
                selected={selectedUser?.user_id === u.user_id}
                onClick={() => setSelectedUser(u)}
              >
                <ListItemText primary={u.user_id} />
              </ListItem>
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
