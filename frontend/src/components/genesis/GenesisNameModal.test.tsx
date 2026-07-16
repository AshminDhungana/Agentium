import { render, screen, fireEvent } from '@testing-library/react';
import { GenesisNameModal } from './GenesisNameModal';
import { useWebSocketStore } from '@/store/websocketStore';

describe('GenesisNameModal', () => {
  it('submits the entered name', () => {
    const submit = vi.fn().mockResolvedValue(true);
    useWebSocketStore.setState({
      genesisAwaitingName: true,
      genesisNamePrompt: 'Name your nation',
      genesisNameTimeout: 60,
      submitCountryName: submit,
    });
    render(<GenesisNameModal />);
    expect(screen.getByText('Name your nation')).toBeTruthy();
    const input = screen.getByPlaceholderText('Enter nation name') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Veridia' } });
    fireEvent.click(screen.getByText('Establish Nation'));
    expect(submit).toHaveBeenCalledWith('Veridia');
  });
});
