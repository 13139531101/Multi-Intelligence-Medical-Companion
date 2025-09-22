import React from 'react';
import { useRecoilState } from 'recoil';
import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Button,
  TextField,
  Box,
  Typography,
  CircularProgress, // For loading indicators
  Alert // For errors
} from '@mui/material';
import { agentDialogState } from '../store/recoilState';
import { getAgentCard, addRemoteAgent } from '../api/api';

function AddAgentDialog({ onAgentAdded }) {
  const [state, setState] = useRecoilState(agentDialogState);

  const handleClose = () => {
    // Reset state on close/cancel
    setState({
      isOpen: false,
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

  const handleAddressChange = (event) => {
    // Clear agent info and error when address changes
    setState(prev => ({
        ...prev,
        agentAddress: event.target.value,
        agentName: '',
        agentDescription: '',
        inputModes: [],
        outputModes: [],
        streamSupported: false,
        pushNotificationsSupported: false,
        error: '',
        agentFrameworkType: '',
    }));
  };

  // Corresponds to load_agent_info
  const handleLoadAgentInfo = async () => {
    if (!state.agentAddress) {
      setState(prev => ({ ...prev, error: 'Please enter an Agent Address.' }));
      return;
    }
    setState(prev => ({ ...prev, isLoadingInfo: true, error: '' }));
    try {
      const agentCard = await getAgentCard(state.agentAddress);
      if (agentCard) {
        setState(prev => ({
          ...prev,
          agentName: agentCard.name,
          agentDescription: agentCard.description,
          agentFrameworkType: agentCard.provider?.organization || '',
          inputModes: agentCard.defaultInputModes,
          outputModes: agentCard.defaultOutputModes,
          streamSupported: agentCard.capabilities?.streaming ?? false,
          pushNotificationsSupported: agentCard.capabilities?.pushNotifications ?? false,
          isLoadingInfo: false,
        }));
      } else {
           // Should be caught by the catch block, but just in case
           setState(prev => ({ ...prev, error: `Could not retrieve info for ${state.agentAddress}`, isLoadingInfo: false }));
      }
    } catch (error) {
      console.error("Error loading agent info:", error);
      setState(prev => ({
        ...prev,
        agentName: '', // Clear name on error
        error: error.message || `Cannot connect to agent at ${state.agentAddress}`,
        isLoadingInfo: false,
      }));
    }
  };

  // Corresponds to save_agent
  const handleSaveAgent = async () => {
    setState(prev => ({ ...prev, isSaving: true, error: '' }));
    try {
      const success = await addRemoteAgent(state.agentAddress);
      if (success) {
        handleClose(); // Close dialog
        onAgentAdded(); // Callback to refresh list on parent page
      } else {
          // Should be caught by the catch block
           setState(prev => ({ ...prev, error: 'Failed to save agent. Unknown error.', isSaving: false }));
      }
    } catch (error) {
        console.error("Error saving agent:", error);
        setState(prev => ({
            ...prev,
            error: error.message || 'Failed to save agent.',
            isSaving: false
        }));
    }
  };


  return (
    <Dialog open={state.isOpen} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add Remote Agent</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
          <TextField
            autoFocus
            margin="dense"
            id="agent-address"
            label="Agent Address"
            type="text"
            fullWidth
            variant="outlined"
            placeholder="localhost:10000"
            value={state.agentAddress}
            onChange={handleAddressChange}
            onBlur={handleAddressChange} // Or keep onBlur if specific logic needed
            disabled={state.isLoadingInfo || state.isSaving}
          />

          {/* Display Error */}
          {state.error && (
             <Alert severity="error" sx={{ mt: 1 }}>{state.error}</Alert>
          )}

          {/* Display Agent Info */}
          {state.agentName && !state.error && (
            <Box sx={{ mt: 2, p: 2, border: '1px dashed grey', borderRadius: 1 }}>
              <Typography variant="subtitle1" gutterBottom>Agent Details:</Typography>
              <Typography><strong>Name:</strong> {state.agentName}</Typography>
              {state.agentDescription && <Typography><strong>Description:</strong> {state.agentDescription}</Typography>}
              {state.agentFrameworkType && <Typography><strong>Framework Type:</strong> {state.agentFrameworkType}</Typography>}
              {state.inputModes.length > 0 && <Typography><strong>Input Modes:</strong> {state.inputModes.join(', ')}</Typography>}
              {state.outputModes.length > 0 && <Typography><strong>Output Modes:</strong> {state.outputModes.join(', ')}</Typography>}
              <Typography><strong>Streaming Supported:</strong> {state.streamSupported ? 'Yes' : 'No'}</Typography>
              <Typography><strong>Push Notifications Supported:</strong> {state.pushNotificationsSupported ? 'Yes' : 'No'}</Typography>
            </Box>
          )}

           {/* Loading indicator for fetching info */}
           {state.isLoadingInfo && <Box sx={{display: 'flex', justifyContent:'center', my: 2}}><CircularProgress size={24} /></Box>}

        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        {/* Logic for buttons mirrors mesop code */}
        {!state.agentName && (
          <Button
            onClick={handleLoadAgentInfo}
            variant="outlined"
            disabled={!state.agentAddress || state.isLoadingInfo || state.isSaving}
          >
             {state.isLoadingInfo ? <CircularProgress size={20} sx={{mr: 1}} /> : null}
            Read Info
          </Button>
        )}
        {state.agentName && !state.error && (
          <Button
            onClick={handleSaveAgent}
            variant="contained"
            color="primary"
            disabled={state.isSaving || state.isLoadingInfo}
            >
             {state.isSaving ? <CircularProgress size={20} sx={{mr: 1}} color="inherit"/> : null}
            Save
          </Button>
        )}
        <Button onClick={handleClose} disabled={state.isLoadingInfo || state.isSaving}>Cancel</Button>
      </DialogActions>
    </Dialog>
  );
}

export default AddAgentDialog;