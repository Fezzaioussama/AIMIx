import { describe, expect, it } from 'vitest';

import {
  bareLink,
  linkHost,
  linkLabel,
  linksIn,
  sameAddress,
  sourceLabel,
  toWebAddress,
} from './webLinks';

describe('linksIn', () => {
  it('finds the web links in typed text, without the punctuation after them', () => {
    expect(
      linksIn('Read https://example.com/a, then (see http://news.example.org/b). Done!'),
    ).toEqual(['https://example.com/a', 'http://news.example.org/b']);
  });

  it('keeps a closing bracket that belongs to the link', () => {
    expect(linksIn('See https://en.wikipedia.org/wiki/Mercury_(planet).')).toEqual([
      'https://en.wikipedia.org/wiki/Mercury_(planet)',
    ]);
  });

  it('ignores what is not a web link', () => {
    expect(linksIn('mail me at a@b.com or ftp://files.example.com, or example.com')).toEqual([]);
  });
});

describe('bareLink', () => {
  it('is the link when a field holds nothing else', () => {
    expect(bareLink('  https://example.com/report  \n')).toBe('https://example.com/report');
  });

  it('is null for text around a link, several links, or no link', () => {
    expect(bareLink('Summarise https://example.com/report')).toBeNull();
    expect(bareLink('https://a.example https://b.example')).toBeNull();
    expect(bareLink('example.com')).toBeNull();
    expect(bareLink('')).toBeNull();
  });
});

describe('toWebAddress', () => {
  it('reads a typed address, adding https:// when it was left out', () => {
    expect(toWebAddress(' https://example.com/a?b=1 ')).toBe('https://example.com/a?b=1');
    expect(toWebAddress('www.example.com/page')).toBe('https://www.example.com/page');
  });

  it('is null for what cannot be a web address', () => {
    expect(toWebAddress('')).toBeNull();
    expect(toWebAddress('   ')).toBeNull();
    expect(toWebAddress('not a link')).toBeNull();
    expect(toWebAddress('mailto:a@b.com')).toBeNull();
  });
});

describe('naming a link', () => {
  it('shows the host and path, without the scheme and www', () => {
    expect(linkLabel('https://www.example.com/blog/post')).toBe('example.com/blog/post');
    expect(linkLabel('https://example.com/')).toBe('example.com');
    expect(linkHost('https://www.example.com/blog/post')).toBe('example.com');
  });

  it('shortens a long one in the middle, keeping both ends', () => {
    const label = linkLabel(`https://example.com/${'a'.repeat(30)}/${'b'.repeat(30)}/end`);
    expect(label).toHaveLength(48);
    expect(label.startsWith('example.com/aaa')).toBe(true);
    expect(label.endsWith('bbb/end')).toBe(true);
    expect(label).toContain('…');
  });

  it('decodes what the address encodes', () => {
    expect(linkLabel('https://fr.wikipedia.org/wiki/%C3%89t%C3%A9')).toBe(
      'fr.wikipedia.org/wiki/Été',
    );
  });

  it('names a file by its name, and a page by its link', () => {
    expect(sourceLabel('report.pdf')).toBe('report.pdf');
    expect(sourceLabel('https://www.example.com/a')).toBe('example.com/a');
  });

  it('tells two ways of writing one address apart from two addresses', () => {
    expect(sameAddress('https://example.com', 'https://example.com/')).toBe(true);
    expect(sameAddress('https://example.com/a', 'https://example.com/b')).toBe(false);
    expect(sameAddress('report.pdf', 'https://example.com/')).toBe(false);
  });
});
