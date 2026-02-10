DO $$
DECLARE
  user_id uuid;
  org_uuid uuid := '12345678-1234-1234-1234-123456789012'::uuid;
  org_id_text text;
BEGIN
  SELECT id INTO user_id
  FROM public."user"
  WHERE name = 'ckan_admin';

  IF NOT EXISTS (
    SELECT 1 FROM public."group" g
    WHERE g.name = 'auscope' AND g.type = 'organization'
  ) THEN
    INSERT INTO public."group"
      (id, name, title, description, state, type, approval_status, image_url, is_organization)
    VALUES
      (
        org_uuid,
        'auscope',
        'AuScope',
        'AuScope is Australia''s provider of research infrastructure to the national geoscience community working on fundamental geoscience questions and grand challenges — climate change, natural resources security and natural hazards. We are funded by the Australian Government via the Department of Education (NCRIS). You can find our team, tools, data, analytics and services at Geoscience Australia, CSIRO, state and territory geological surveys and universities across the Australian continent.',
        'active',
        'organization',
        'approved',
        'https://images.squarespace-cdn.com/content/v1/5b440dc18ab722131f76b631/1544673461662-GWIIUQIW3A490WP1RHBV/AuScope+Logo_no+space_+-+horizontal+tagline_+-+horizontal+tagline.png',
        true
      );
  END IF;

  -- Re-read org id from DB, and keep both forms
  SELECT id INTO org_uuid
  FROM public."group"
  WHERE name = 'auscope' AND type = 'organization'
  LIMIT 1;

  org_id_text := org_uuid::text;

  -- Membership: in your DB member.group_id and member.table_id are TEXT
  IF user_id IS NOT NULL THEN
    IF NOT EXISTS (
      SELECT 1
      FROM public.member m
      WHERE m.group_id   = org_id_text
        AND m.table_name = 'user'
        AND m.table_id   = user_id::text
        AND m.capacity   = 'admin'
    ) THEN
      INSERT INTO public.member
        (id, group_id, table_id, state, table_name, capacity)
      VALUES
        ('abcdefgh-abcd-abcd-abcd-abcdefghijkl', org_id_text, user_id::text, 'active', 'user', 'admin');
    END IF;
  END IF;
END $$;
