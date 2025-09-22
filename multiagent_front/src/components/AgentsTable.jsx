import React from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Typography,
  Chip // For boolean values
} from '@mui/material';

/**
 * @param {{ agents: AgentCard[] }} props
 */
function AgentsTable({ agents }) {
  if (!agents || agents.length === 0) {
    return <Typography sx={{mt: 2, textAlign: 'center'}}>No remote agents found.</Typography>;
  }

  // Column definitions similar to the pandas DataFrame setup
  const columns = [
    { id: 'address', label: 'Address', minWidth: 170 },
    { id: 'name', label: 'Name', minWidth: 150 },
    { id: 'description', label: 'Description', minWidth: 200 },
    { id: 'organization', label: 'Organization', minWidth: 100 },
    { id: 'inputModes', label: 'Input Modes', minWidth: 150 },
    { id: 'outputModes', label: 'Output Modes', minWidth: 150 },
    { id: 'streaming', label: 'Streaming', minWidth: 80, align: 'center' },
  ];

  return (
    <Paper sx={{ width: '100%', overflow: 'hidden' }}>
      <TableContainer sx={{ maxHeight: 600 }}> {/* Add scroll if needed */}
        <Table stickyHeader aria-label="sticky table">
          <TableHead>
            <TableRow>
              {columns.map((column) => (
                <TableCell
                  key={column.id}
                  align={column.align || 'left'}
                  style={{ minWidth: column.minWidth }}
                  sx={{ fontWeight: 'bold' }} // Make headers bold
                >
                  {column.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {agents.map((agent) => (
              <TableRow hover role="checkbox" tabIndex={-1} key={agent.url || agent.name}>
                <TableCell>{agent.url}</TableCell>
                <TableCell>{agent.name}</TableCell>
                <TableCell>{agent.description}</TableCell>
                <TableCell>{agent.provider?.organization || 'N/A'}</TableCell>
                <TableCell>{agent.defaultInputModes.join(', ')}</TableCell>
                <TableCell>{agent.defaultOutputModes.join(', ')}</TableCell>
                <TableCell align="center">
                   <Chip
                      label={agent.capabilities?.streaming ? 'Yes' : 'No'}
                      color={agent.capabilities?.streaming ? 'success' : 'default'}
                      size="small"
                    />
                </TableCell>
                {/* Add Push Notifications column if needed */}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}

export default AgentsTable;