package github

import "testing"

func TestParseRepositoryURLHTTPS(t *testing.T) {
	repo, err := ParseRepositoryURL("https://github.com/opsdevcode/tf-aws-example.git")
	if err != nil {
		t.Fatalf("ParseRepositoryURL: %v", err)
	}
	if repo.Owner != "opsdevcode" || repo.Name != "tf-aws-example" {
		t.Fatalf("got %+v", repo)
	}
}

func TestParseRepositoryURLSSH(t *testing.T) {
	repo, err := ParseRepositoryURL("git@github.com:acme/module.git")
	if err != nil {
		t.Fatalf("ParseRepositoryURL: %v", err)
	}
	if repo.Owner != "acme" || repo.Name != "module" {
		t.Fatalf("got %+v", repo)
	}
}
