import { describe, it } from 'vitest';
import { auditRoute } from '@/test/a11yBrowser';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';

describe('Card color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(
      <Card>
        <CardHeader>
          <CardTitle>Card Title</CardTitle>
          <CardDescription>Card description helper text</CardDescription>
        </CardHeader>
        <CardContent>Card body content</CardContent>
      </Card>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <Card>
        <CardHeader>
          <CardTitle>Card Title</CardTitle>
          <CardDescription>Task helper description</CardDescription>
        </CardHeader>
        <CardContent>Card body content</CardContent>
      </Card>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});
