import { render, screen, fireEvent, waitFor, waitForElementToBeRemoved } from '@testing-library/react';
import { GenesisNameModal } from './GenesisNameModal';
import { useWebSocketStore } from '@/store/websocketStore';

describe('GenesisNameModal', () => {
  it('submits the entered name and hides the modal', async () => {
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
    // On success the store clears the awaiting flag and the modal hides
    // (no late `awaiting_name` poll should re-show it).
    await waitForElementToBeRemoved(() => screen.queryByText('Name your nation'));
  });

  it('uses the default name when the input is empty', async () => {
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
    await waitForElementToBeRemoved(() => screen.queryByText('Name your nation'));
  });

  it('surfaces a warning and dismisses when genesis no longer awaits the name', async () => {
    const submit = vi.fn().mockResolvedValue(false);
    const dismiss = vi.fn();
    useWebSocketStore.setState({
      genesisAwaitingName: true,
      genesisNamePrompt: 'Name your nation',
      genesisNameTimeout: 60,
      submitCountryName: submit,
      dismissGenesisNamePrompt: dismiss,
    });
    render(<GenesisNameModal />);
    const input = screen.getByPlaceholderText('Enter nation name') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Veridia' } });
    fireEvent.click(screen.getByText('Establish Nation'));
    expect(submit).toHaveBeenCalledWith('Veridia');
    // Rejected (e.g. the 60s prompt timed out) — the failure is surfaced and
    // the modal is dismissed instead of silently losing the name.
    await waitFor(() => expect(dismiss).toHaveBeenCalled());
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
