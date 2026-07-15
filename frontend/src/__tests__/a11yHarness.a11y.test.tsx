import { checkA11y } from '@/test/a11y';

test('harness passes a properly named button', async () => {
  await checkA11y(<button aria-label="Close">×</button>);
});

test('harness catches a button with no accessible name', async () => {
  await expect(
    checkA11y(
      <button>
        <span aria-hidden="true">×</span>
      </button>
    )
  ).rejects.toBeDefined();
});
