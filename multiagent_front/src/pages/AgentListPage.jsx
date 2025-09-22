import React, { useEffect, useState, useCallback } from 'react';
import { useRecoilState, useSetRecoilState } from 'recoil';
import { Container, Box, Button, CircularProgress, Alert } from '@mui/material';
import AddIcon from '@mui/icons-material/Add'; // Or 'Upload' if you prefer
import Header from './Header';
import AgentsTable from '../components/AgentsTable';
import AddAgentDialog from '../components/AddAgentDialog';
import { remoteAgentsListState, agentDialogState } from '../store/recoilState';
import { listRemoteAgents } from '../api/api';

function AgentListPage() {
  const [agents, setAgents] = useRecoilState(remoteAgentsListState);
  const setDialogState = useSetRecoilState(agentDialogState);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  // Function to fetch agents, wrapped in useCallback for stability
  const fetchAgents = useCallback(async () => {
    setIsLoading(true);
    setError('');
    try {
      const fetchedAgents = await listRemoteAgents();
      setAgents(fetchedAgents);
    } catch (err) {
      setError('Failed to load remote agents. Please ensure the backend service is running.');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [setAgents]); // Dependency on setAgents

  // Fetch agents on component mount
  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]); // Depend on the stable fetchAgents function

  // Corresponds to add_agent Mesop function
  const handleOpenAddAgentDialog = () => {
    // Reset dialog state and open it
     setDialogState({
        isOpen: true,
        agentAddress: '',
        agentName: '',
        agentDescription: '',
        inputModes: [],
        outputModes: [],
        streamSupported: false,
        pushNotificationsSupported: false,
        error: '',
        agentFrameworkType: '',
        isLoadingInfo: false,
        isSaving: false,
     });
  };

  return (
    <div> 
      {/* 独立的 Header，在 Container 外面 */}
      <Header title="Remote Agents" iconName="smart_toy" />

      <Container maxWidth="lg" sx={{ mt: 3 }}> {/* 内容区域有顶部外边距 */}
        {/* Loading State */}
        {isLoading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', my: 5 }}>
            <CircularProgress />
          </Box>
        )}

        {/* Error State */}
        {error && !isLoading && (
          <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
        )}

        {/* Content */}
        {!isLoading && !error && (
          <Box>
            <AgentsTable agents={agents} />
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={handleOpenAddAgentDialog}
              >
                Add Agent
              </Button>
            </Box>
          </Box>
        )}

        <AddAgentDialog onAgentAdded={fetchAgents} />
      </Container>
    </div>
  );
}

export default AgentListPage;