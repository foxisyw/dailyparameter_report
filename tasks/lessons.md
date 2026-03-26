# Lessons

- When parsing Lark-style summaries, only treat explicit heading lines as section boundaries. Keyword-only matching is too loose and will swallow ordinary content lines.
- When extracting user identifiers from free-form alert text, handle paired `UID + master_user_id` first and deduplicate afterwards. Otherwise the same suspect gets counted multiple times.
- For date-sensitive local workflows, verify the actual shell clock (`TZ=Asia/Hong_Kong date`) before assuming "today". The workspace metadata date can lag behind the real runtime date.
- Never let fixture data participate in the default production path. Test fixtures must require an explicit flag or explicit input path.
- Do not use one broad cache policy for HTML, JSON, and hashed assets. The app shell and report data need revalidation; only versioned asset files should be aggressively cached.
