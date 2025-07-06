
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile

class UserProfileRegistrationForm(UserCreationForm):
    name = forms.CharField(max_length=100, required=True)
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=20, required=False)
    user_type = forms.ChoiceField(choices=UserProfile.USER_TYPE_CHOICES, required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email',) # Add email to User model fields

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email'] # Save email to User model
        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                name=self.cleaned_data['name'],
                email=self.cleaned_data['email'],
                phone_number=self.cleaned_data['phone_number'],
                user_type=self.cleaned_data['user_type'] # Save user_type
            )
        return user
