import { render, screen, fireEvent } from '@testing-library/react';
import { GenesisNameModal } from './GenesisNameModal';
import { useWebSocketStore } from '@/store/websocketStore';

describe('GenesisNameModal', () => {
  it('submits the entered name', () => {
    const submit = vi.fn().mockResolvedValue(true);
    const dismiss = vi.fn();
    useWebSocketStore.setState({
      genesisAwaitingName: true,
      genesisNamePrompt: 'Name your nation',
      genesisNameTimeout: 60,
      submitCountryName: submit,
      dismissGenesisNamePrompt: dismiss,
    });
    render(<GenesisNameModal />);
    expect(screen.getByText('Name your nation')).toBeTruthy();
    const input = screen.getByPlaceholderText('Enter nation name') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Veridia' } });
    fireEvent.click(screen.getByText('Establish Nation'));
    expect(submit).toHaveBeenCalledWith('Veridia');
    // Modal is dismissed immediately so processing continues in the background.
    expect(dismiss).toHaveBeenCalled();
  });

  it('uses the default name when the input is empty', () => {
    const submit = vi.fn().mockResolvedValue(true);
    const dismiss = vi.fn();
    useWebSocketStore.setState({
      genesisAwaitingName: true,
      genesisNamePrompt: 'Name your nation',
      genesisNameTimeout: 60,
      submitCountryName: submit,
      dismissGenesisNamePrompt: dismiss,
    });
    render(<GenesisNameModal />);
    const button = screen.getByText('Use Default Name') as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    fireEvent.click(button);
    expect(submit).toHaveBeenCalledWith('');
    expect(dismiss).toHaveBeenCalled();
  });

  it('renders the prompt as formatted Markdown, not raw source', () => {
    const submit = vi.fn().mockResolvedValue(true);
    useWebSocketStore.setState({
      genesisAwaitingName: true,
      genesisNamePrompt: '**Welcome to Agentium**\n\nReply with `name: Foo`',
      genesisNameTimeout: 60,
      submitCountryName: submit,
    });
    const { container } = render(<GenesisNameModal />);
    // Bold is rendered as a <strong> element, not literal ** characters.
    expect(container.querySelector('strong')?.textContent).toBe('Welcome to Agentium');
    // Inline code is rendered as a <code> element, not literal backticks.
    expect(container.querySelector('code')?.textContent).toBe('name: Foo');
    expect(container.textContent).not.toContain('**Welcome to Agentium**');
  });
});
